import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException
from firebase_admin import auth
from src.auth import firebase_service as service


class FirebaseServiceTests(unittest.TestCase):
    def setUp(self):
        self.identity = {
            "uid": "firebase-user",
            "email": "reader@example.com",
            "firebase": {"sign_in_provider": "password"},
        }
        for name, patcher in (
            ("request", patch.object(service.requests, "post")),
            (
                "verify",
                patch.object(
                    service.auth, "verify_id_token", return_value=self.identity
                ),
            ),
            ("app", patch.object(service, "firebase_app", return_value="test-app")),
        ):
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.response = Mock(status_code=200)
        self.response.json.return_value = {"idToken": "firebase-id-token"}
        self.request.return_value = self.response
        env = patch.dict(os.environ, {"FIREBASE_WEB_API_KEY": "test-api-key"})
        env.start()
        self.addCleanup(env.stop)

    def authenticate(self):
        return service.authenticate(
            "signInWithPassword", "reader@example.com", "test-password"
        )

    def test_password_api_and_id_token_are_both_verified(self):
        self.assertEqual(
            self.authenticate(), {"uid": "firebase-user", "email": "reader@example.com"}
        )
        self.request.assert_called_once_with(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": "test-api-key"},
            json={
                "email": "reader@example.com",
                "password": "test-password",
                "returnSecureToken": True,
            },
            timeout=10,
        )
        self.verify.assert_called_once_with(
            "firebase-id-token", app="test-app", check_revoked=True
        )

    def test_firebase_error_codes_are_mapped_without_leaking_remote_errors(self):
        self.response.status_code = 400
        for code, status in (
            ("EMAIL_EXISTS", 409),
            ("INVALID_LOGIN_CREDENTIALS", 401),
            ("INVALID_PASSWORD", 401),
            ("EMAIL_NOT_FOUND", 401),
            ("USER_DISABLED", 403),
            ("TOO_MANY_ATTEMPTS_TRY_LATER", 429),
            ("WEAK_PASSWORD : rules", 422),
            ("OPERATION_NOT_ALLOWED", 503),
            ("API_KEY_INVALID", 503),
        ):
            with self.subTest(code=code):
                self.response.json.return_value = {"error": {"message": code}}
                with self.assertRaises(HTTPException) as caught:
                    self.authenticate()
                self.assertEqual(caught.exception.status_code, status)
        self.verify.assert_not_called()

    def test_missing_key_network_failure_and_invalid_response_are_unavailable(self):
        with patch.dict(os.environ, {"FIREBASE_WEB_API_KEY": ""}):
            with self.assertRaises(HTTPException) as caught:
                self.authenticate()
            self.assertEqual(caught.exception.status_code, 503)
        self.request.side_effect = requests.ConnectionError("offline")
        with self.assertRaises(HTTPException) as caught:
            self.authenticate()
        self.assertEqual(caught.exception.status_code, 503)
        self.request.side_effect = None
        self.response.json.side_effect = ValueError("invalid JSON")
        with self.assertRaises(HTTPException) as caught:
            self.authenticate()
        self.assertEqual(caught.exception.status_code, 503)

    def test_invalid_revoked_or_disabled_token_is_rejected(self):
        for error, status in (
            (ValueError("invalid token"), 401),
            (auth.RevokedIdTokenError("revoked"), 401),
            (auth.UserDisabledError("disabled"), 403),
            (auth.CertificateFetchError("offline", None), 503),
        ):
            self.verify.side_effect = error
            with self.assertRaises(HTTPException) as caught:
                self.authenticate()
            self.assertEqual(caught.exception.status_code, status)

    def test_wrong_email_missing_uid_and_non_password_identity_are_rejected(self):
        for identity in (
            {**self.identity, "email": "other@example.com"},
            {**self.identity, "uid": ""},
            {**self.identity, "email": None},
            {**self.identity, "firebase": {"sign_in_provider": "google.com"}},
        ):
            self.verify.return_value = identity
            with self.assertRaises(HTTPException) as caught:
                self.authenticate()
            self.assertEqual(caught.exception.status_code, 401)

    def test_password_reset_uses_firebase_email_action_without_signing_in(self):
        self.response.json.return_value = {"email": "reader@example.com"}
        self.assertIsNone(service.send_password_reset_email("reader@example.com"))
        self.request.assert_called_once_with(
            "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode",
            params={"key": "test-api-key"},
            json={"requestType": "PASSWORD_RESET", "email": "reader@example.com"},
            timeout=10,
        )
        self.verify.assert_not_called()

    def test_password_reset_does_not_disclose_missing_email(self):
        self.response.status_code = 400
        self.response.json.return_value = {"error": {"message": "EMAIL_NOT_FOUND"}}
        self.assertIsNone(service.send_password_reset_email("missing@example.com"))
        # Đăng nhập vẫn phải từ chối email chưa đăng ký.
        with self.assertRaises(HTTPException) as caught:
            self.authenticate()
        self.assertEqual(caught.exception.status_code, 401)
        self.verify.assert_not_called()

    def test_password_reset_reports_quota_and_service_errors(self):
        self.response.status_code = 400
        for code, status in (
            ("TOO_MANY_ATTEMPTS_TRY_LATER", 429),
            ("QUOTA_EXCEEDED", 429),
            ("OPERATION_NOT_ALLOWED", 503),
        ):
            with self.subTest(code=code):
                self.response.json.return_value = {"error": {"message": code}}
                with self.assertRaises(HTTPException) as caught:
                    service.send_password_reset_email("reader@example.com")
                self.assertEqual(caught.exception.status_code, status)
        self.request.side_effect = requests.ConnectionError("offline")
        with self.assertRaises(HTTPException) as caught:
            service.send_password_reset_email("reader@example.com")
        self.assertEqual(caught.exception.status_code, 503)

    def test_google_token_requires_google_provider_and_verified_email(self):
        self.verify.return_value = {
            **self.identity,
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        result = service.verify_identity("google-firebase-id-token", "google.com")
        self.assertEqual(
            result, {"uid": "firebase-user", "email": "reader@example.com"}
        )
        self.verify.assert_called_once_with(
            "google-firebase-id-token", app="test-app", check_revoked=True
        )
        self.request.assert_not_called()
        for verified in (False, None, "true"):
            self.verify.return_value = {
                **self.identity,
                "email_verified": verified,
                "firebase": {"sign_in_provider": "google.com"},
            }
            with self.assertRaises(HTTPException) as caught:
                service.verify_identity("token", "google.com")
            self.assertEqual(caught.exception.status_code, 401)
        self.verify.return_value = {**self.identity, "email_verified": True}
        with self.assertRaises(HTTPException) as caught:
            service.verify_identity("password-token", "google.com")
        self.assertEqual(caught.exception.status_code, 401)

    def test_google_id_token_is_exchanged_with_firebase_before_backend_verification(
        self,
    ):
        self.app.return_value = SimpleNamespace(project_id="test-project")
        self.verify.return_value = {
            **self.identity,
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        }
        result = service.authenticate_google("google-token&special=1")
        self.assertEqual(
            result, {"uid": "firebase-user", "email": "reader@example.com"}
        )
        self.request.assert_called_once_with(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp",
            params={"key": "test-api-key"},
            json={
                "requestUri": "https://test-project.firebaseapp.com/__/auth/handler",
                "postBody": "id_token=google-token%26special%3D1&providerId=google.com",
                "returnSecureToken": True,
            },
            timeout=10,
        )
        self.verify.assert_called_once_with(
            "firebase-id-token", app=self.app.return_value, check_revoked=True
        )

    def test_google_account_conflict_does_not_verify_or_issue_a_token(self):
        self.app.return_value = SimpleNamespace(project_id="test-project")
        self.response.json.return_value = {"needConfirmation": True}
        with self.assertRaises(HTTPException) as caught:
            service.authenticate_google("google-token")
        self.assertEqual(caught.exception.status_code, 409)
        self.verify.assert_not_called()

    def test_google_exchange_rejects_invalid_google_token(self):
        self.app.return_value = SimpleNamespace(project_id="test-project")
        self.response.status_code = 400
        self.response.json.return_value = {
            "error": {"message": "INVALID_IDP_RESPONSE : Invalid id_token"}
        }
        with self.assertRaises(HTTPException) as caught:
            service.authenticate_google("fake-google-token")
        self.assertEqual(caught.exception.status_code, 401)
        self.verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
