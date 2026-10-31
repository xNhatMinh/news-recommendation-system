import os
from urllib.parse import urlencode

import requests
from fastapi import HTTPException
from firebase_admin import auth, exceptions


def firebase_app():
    from src.notifications.firebase_config import firebase_app as app

    return app


def firebase_request(action, payload):
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise HTTPException(503, "Authentication service is not configured")
    try:
        response = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:{action}",
            params={"key": api_key},
            json=payload,
            timeout=10,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        raise HTTPException(503, "Authentication service is unavailable") from None

    if not isinstance(data, dict):
        raise HTTPException(503, "Authentication service is unavailable")
    if response.status_code != 200:
        error = data.get("error", {}).get("message", "")
        code = error.split(" : ")[0]
        # Cùng phản hồi khi email chưa tồn tại để không lộ tài khoản đăng ký.
        if action == "sendOobCode" and code == "EMAIL_NOT_FOUND":
            return {}
        if code == "EMAIL_EXISTS":
            raise HTTPException(409, "Email already registered")
        if code in {
            "EMAIL_NOT_FOUND",
            "INVALID_PASSWORD",
            "INVALID_LOGIN_CREDENTIALS",
            "INVALID_EMAIL",
            "INVALID_IDP_RESPONSE",
            "INVALID_ID_TOKEN",
            "INVALID_OAUTH_RESPONSE",
        }:
            raise HTTPException(401, "Email or password is incorrect")
        if code == "USER_DISABLED":
            raise HTTPException(403, "Account is disabled")
        if code.startswith("TOO_MANY_ATTEMPTS") or code == "QUOTA_EXCEEDED":
            raise HTTPException(429, "Too many attempts; try again later")
        if (
            code.startswith("WEAK_PASSWORD")
            or code == "PASSWORD_DOES_NOT_MEET_REQUIREMENTS"
        ):
            raise HTTPException(422, "Password does not meet requirements")
        raise HTTPException(503, "Authentication service is unavailable")

    return data


def authenticate(action, email, password):
    """Firebase kiểm tra mật khẩu, sau đó backend xác minh token trả về."""
    data = firebase_request(
        action, {"email": email, "password": password, "returnSecureToken": True}
    )
    return verify_identity(data.get("idToken", ""), "password", expected_email=email)


def authenticate_google(google_id_token):
    """Đổi Google ID token qua Firebase, rồi xác minh danh tính Firebase."""
    data = firebase_request(
        "signInWithIdp",
        {
            "requestUri": f"https://{firebase_app().project_id}.firebaseapp.com/__/auth/handler",
            "postBody": urlencode(
                {"id_token": google_id_token, "providerId": "google.com"}
            ),
            "returnSecureToken": True,
        },
    )
    if data.get("needConfirmation"):
        raise HTTPException(409, "Account requires linking")
    return verify_identity(data.get("idToken", ""), "google.com")


def verify_identity(id_token, provider, expected_email=None):
    """Xác minh Firebase ID token đúng project, còn hạn và đúng phương thức đăng nhập."""
    try:
        identity = auth.verify_id_token(
            id_token, app=firebase_app(), check_revoked=True
        )
    except auth.UserDisabledError:
        raise HTTPException(403, "Account is disabled") from None
    except auth.CertificateFetchError:
        raise HTTPException(503, "Authentication service is unavailable") from None
    except (auth.InvalidIdTokenError, ValueError):
        raise HTTPException(401, "Invalid authentication token") from None
    except exceptions.FirebaseError:
        raise HTTPException(503, "Authentication service is unavailable") from None
    email = identity.get("email")
    if not identity.get("uid") or not isinstance(email, str) or not email:
        raise HTTPException(401, "Invalid authentication identity")
    if expected_email is not None and email.casefold() != expected_email.casefold():
        raise HTTPException(401, "Invalid authentication identity")
    if identity.get("firebase", {}).get("sign_in_provider") != provider:
        raise HTTPException(401, "Unexpected authentication provider")
    if provider == "google.com" and identity.get("email_verified") is not True:
        raise HTTPException(401, "Google email is not verified")
    return {"uid": identity["uid"], "email": email}


def send_password_reset_email(email):
    """Firebase gửi liên kết, người dùng đặt mật khẩu mới trên trang của Firebase."""
    firebase_request("sendOobCode", {"requestType": "PASSWORD_RESET", "email": email})
