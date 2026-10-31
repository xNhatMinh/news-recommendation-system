import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

with patch.dict(
    os.environ,
    {
        "MYSQL_USER": "test",
        "MYSQL_PASSWORD": "test",
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "test",
    },
):
    from src.api.routes import auth
from src.api.security import decode_access_token


class FirebaseRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.execute(
                text(
                    "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(100) NOT NULL UNIQUE, email VARCHAR(254) UNIQUE, password_hash VARCHAR(255))"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE user_firebase_accounts (user_id INTEGER PRIMARY KEY, firebase_uid VARCHAR(128) UNIQUE)"
                )
            )
            c.execute(
                text("CREATE TABLE user_preferences (user_id INTEGER, topic TEXT)")
            )
        engine_patch = patch.object(auth, "engine", self.engine)
        engine_patch.start()
        self.addCleanup(engine_patch.stop)
        cloud = patch.object(
            auth.firebase_service,
            "authenticate",
            side_effect=lambda action, email, password: {
                "uid": "uid-" + email.lower(),
                "email": email.lower(),
            },
        )
        self.cloud = cloud.start()
        self.addCleanup(cloud.stop)
        google = patch.object(
            auth.firebase_service,
            "authenticate_google",
            return_value={"uid": "google-user", "email": "reader@gmail.com"},
        )
        self.google = google.start()
        self.addCleanup(google.stop)
        app = FastAPI()
        app.include_router(auth.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def register(self, email="reader@example.com", password="a-long-password"):
        return self.client.post(
            "/auth/register", json={"email": email, "password": password}
        )

    def login(self, email="reader@example.com", password="a-long-password"):
        return self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )

    def add_unlinked_profile(self):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO users VALUES (7,'old-reader','reader@example.com','obsolete-password-hash')"
                )
            )
            c.execute(text("INSERT INTO user_preferences VALUES (7,'Thể thao')"))

    def test_register_saves_uid_without_storing_password_in_mysql(self):
        response = self.register()
        self.assertEqual(response.status_code, 201, response.text)
        self.cloud.assert_called_once_with(
            "signUp", "reader@example.com", "a-long-password"
        )
        with self.engine.connect() as c:
            user = c.execute(text("SELECT * FROM users")).mappings().one()
            link = (
                c.execute(text("SELECT * FROM user_firebase_accounts")).mappings().one()
            )
        self.assertIsNone(user["password_hash"])
        self.assertTrue(user["username"].startswith("user_"))
        self.assertEqual(link["user_id"], user["id"])
        self.assertEqual(link["firebase_uid"], "uid-reader@example.com")
        self.assertEqual(set(response.json()), {"user_id", "email", "message"})
        self.assertNotIn("a-long-password", response.text)

    def test_login_reuses_user_id_and_returns_application_jwt(self):
        user_id = self.register().json()["user_id"]
        first = self.login()
        second = self.login()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.json()["user_id"], user_id)
        token = first.json()["access_token"]
        self.assertEqual(decode_access_token(token)["sub"], str(user_id))
        response = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], user_id)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 1)

    def test_firebase_account_can_create_local_profile_on_first_login(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.text)
        with self.engine.connect() as c:
            self.assertIsNone(
                c.execute(text("SELECT password_hash FROM users")).scalar()
            )

    def test_duplicate_email_does_not_call_firebase_registration(self):
        self.register()
        self.cloud.reset_mock()
        self.assertEqual(self.register(email="READER@example.com").status_code, 409)
        self.cloud.assert_not_called()

    def test_invalid_payload_does_not_call_firebase_or_write_user(self):
        for payload in (
            {"email": "invalid", "password": "long-password"},
            {"email": "reader@example.com", "password": "short"},
            {"password": "long-password"},
        ):
            self.assertEqual(
                self.client.post("/auth/register", json=payload).status_code, 422
            )
        self.cloud.assert_not_called()
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 0)

    def test_cloud_errors_do_not_create_local_users(self):
        for code in (401, 403, 409, 429, 503):
            self.cloud.side_effect = HTTPException(code, "Cloud error")
            self.assertEqual(self.register().status_code, code)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 0)

    def test_firebase_rejection_never_uses_local_password_or_retries(self):
        self.add_unlinked_profile()
        self.cloud.side_effect = HTTPException(401, "Invalid credentials")
        response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 401)
        self.cloud.assert_called_once_with(
            "signInWithPassword", "reader@example.com", "wrong-password"
        )
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(text("SELECT COUNT(*) FROM user_firebase_accounts")).scalar(),
                0,
            )

    def test_linked_user_requires_successful_firebase_authentication(self):
        self.add_unlinked_profile()
        with self.engine.begin() as c:
            c.execute(
                text("INSERT INTO user_firebase_accounts VALUES (7,'existing-uid')")
            )
        self.cloud.side_effect = HTTPException(401, "Invalid Firebase password")
        self.assertEqual(self.login(password="old-password").status_code, 401)

    def test_firebase_outage_never_bypasses_authentication(self):
        self.add_unlinked_profile()
        self.cloud.side_effect = HTTPException(503, "Unavailable")
        self.assertEqual(self.login(password="old-password").status_code, 503)

    def test_firebase_login_cannot_claim_an_unlinked_profile(
        self,
    ):
        self.add_unlinked_profile()
        self.assertEqual(self.login(password="new-firebase-password").status_code, 409)
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(text("SELECT COUNT(*) FROM user_firebase_accounts")).scalar(),
                0,
            )

    def test_another_firebase_uid_cannot_reassign_existing_account(self):
        self.register()
        self.cloud.side_effect = lambda *args: {
            "uid": "other-uid",
            "email": "reader@example.com",
        }
        self.assertEqual(self.login().status_code, 409)
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(
                    text("SELECT firebase_uid FROM user_firebase_accounts")
                ).scalar(),
                "uid-reader@example.com",
            )

    def test_password_reset_is_public_and_does_not_touch_mysql_or_issue_tokens(self):
        with patch.object(
            auth.firebase_service, "send_password_reset_email"
        ) as send, patch.object(
            auth.engine,
            "connect",
            side_effect=AssertionError("Unexpected database read"),
        ), patch.object(
            auth.engine,
            "begin",
            side_effect=AssertionError("Unexpected database write"),
        ):
            response = self.client.post(
                "/auth/forgot-password", json={"email": "reader@example.com"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()), {"message"})
        send.assert_called_once_with("reader@example.com")
        self.cloud.assert_not_called()
        self.google.assert_not_called()

    def test_password_reset_rejects_invalid_email_before_calling_firebase(self):
        with patch.object(auth.firebase_service, "send_password_reset_email") as send:
            for payload in (
                {},
                {"email": ""},
                {"email": "invalid"},
                {"email": "a" * 255 + "@example.com"},
            ):
                response = self.client.post("/auth/forgot-password", json=payload)
                self.assertEqual(response.status_code, 422)
            send.assert_not_called()

    def test_password_reset_returns_service_errors_instead_of_success(self):
        for status in (429, 503):
            with self.subTest(status=status), patch.object(
                auth.firebase_service,
                "send_password_reset_email",
                side_effect=HTTPException(status, "Unavailable"),
            ):
                response = self.client.post(
                    "/auth/forgot-password", json={"email": "reader@example.com"}
                )
                self.assertEqual(response.status_code, status)
                self.assertNotIn("access_token", response.json())

    def test_old_jwt_for_unlinked_profile_is_rejected(self):
        self.add_unlinked_profile()
        token = auth.create_access_token(7)
        response = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_repeated_firebase_login_preserves_preferences(self):
        user_id = self.login().json()["user_id"]
        with self.engine.begin() as c:
            c.execute(
                text("INSERT INTO user_preferences VALUES (:id, 'Thể thao')"),
                {"id": user_id},
            )
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], user_id)
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(
                    text("SELECT topic FROM user_preferences WHERE user_id=:id"),
                    {"id": user_id},
                ).scalar(),
                "Thể thao",
            )

    def test_google_new_account_gets_jwt_and_repeated_login_reuses_profile(self):
        first = self.client.post(
            "/auth/google", json={"id_token": "firebase-google-token"}
        )
        second = self.client.post(
            "/auth/google", json={"id_token": "firebase-google-token"}
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["user_id"], second.json()["user_id"])
        self.assertEqual(
            decode_access_token(first.json()["access_token"])["sub"],
            str(first.json()["user_id"]),
        )
        self.google.assert_called_with("firebase-google-token")
        self.cloud.assert_not_called()
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 1)
            self.assertIsNone(
                c.execute(text("SELECT password_hash FROM users")).scalar()
            )

    def test_google_and_password_login_use_same_profile_for_same_firebase_uid(self):
        user_id = self.register(email="reader@gmail.com").json()["user_id"]
        self.google.return_value = {
            "uid": "uid-reader@gmail.com",
            "email": "reader@gmail.com",
        }
        response = self.client.post("/auth/google", json={"id_token": "google-token"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user_id"], user_id)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 1)

    def test_google_cannot_replace_different_uid_already_bound_to_same_gmail(self):
        user_id = self.register(email="reader@gmail.com").json()["user_id"]
        response = self.client.post(
            "/auth/google", json={"id_token": "other-google-token"}
        )
        self.assertEqual(response.status_code, 409)
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(
                    text(
                        "SELECT firebase_uid FROM user_firebase_accounts WHERE user_id=:id"
                    ),
                    {"id": user_id},
                ).scalar(),
                "uid-reader@gmail.com",
            )

    def test_google_cannot_claim_an_unlinked_profile(self):
        self.add_unlinked_profile()
        with self.engine.begin() as c:
            c.execute(text("UPDATE users SET email='reader@gmail.com' WHERE id=7"))
        self.assertEqual(
            self.client.post("/auth/google", json={"id_token": "token"}).status_code,
            409,
        )
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(text("SELECT COUNT(*) FROM user_firebase_accounts")).scalar(),
                0,
            )

    def test_invalid_google_token_never_creates_user(self):
        self.google.side_effect = HTTPException(401, "Invalid token")
        self.assertEqual(
            self.client.post("/auth/google", json={"id_token": "fake"}).status_code, 401
        )
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM users")).scalar(), 0)

    def test_google_token_validation_and_client_email_is_not_trusted(self):
        for payload in ({}, {"id_token": ""}, {"id_token": "x" * 10001}):
            self.assertEqual(
                self.client.post("/auth/google", json=payload).status_code, 422
            )
        self.google.assert_not_called()
        response = self.client.post(
            "/auth/google",
            json={"id_token": "real-token", "email": "victim@gmail.com", "user_id": 7},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["email"], "reader@gmail.com")


if __name__ == "__main__":
    unittest.main()
