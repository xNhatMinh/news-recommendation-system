from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    GoogleLoginRequest,
    PasswordResetRequest,
    PasswordResetResponse,
)
from src.api.security import create_access_token, get_token_payload
from src.auth import firebase_service
from src.db.db import engine

router = APIRouter(prefix="/auth", tags=["Auth"])


def find_user_by_email(email):
    with engine.connect() as connection:
        return (
            connection.execute(
                text("""
            SELECT id, email FROM users WHERE LOWER(email) = LOWER(:email)
        """),
                {"email": email},
            )
            .mappings()
            .first()
        )


def linked_user(connection, uid):
    return (
        connection.execute(
            text("""
        SELECT u.id AS user_id, u.email
        FROM users u JOIN user_firebase_accounts f ON f.user_id = u.id
        WHERE f.firebase_uid = :uid
    """),
            {"uid": uid},
        )
        .mappings()
        .first()
    )


def sync_firebase_user(identity):
    """Tìm hoặc tạo hồ sơ MySQL theo UID đã được Firebase xác minh."""
    uid, email = identity["uid"], identity["email"]
    try:
        with engine.begin() as connection:
            user = linked_user(connection, uid)
            if user is not None:
                return dict(user)
            existing = connection.execute(
                text("SELECT id FROM users WHERE LOWER(email) = LOWER(:email)"),
                {"email": email},
            ).first()
            if existing is not None:
                raise HTTPException(409, "Email already registered to another account")
            result = connection.execute(
                text("""
                INSERT INTO users (username, email)
                VALUES (:username, :email)
                """),
                {"username": f"user_{uuid4().hex}", "email": email},
            )
            user_id = result.lastrowid
            connection.execute(
                text("""
                INSERT INTO user_firebase_accounts (user_id, firebase_uid)
                VALUES (:user_id, :uid)
            """),
                {"user_id": user_id, "uid": uid},
            )
            return {"user_id": user_id, "email": email}
    except IntegrityError as exc:
        duplicate = (
            exc.orig.args and exc.orig.args[0] == 1062
        ) or "UNIQUE constraint failed" in str(exc.orig)
        if not duplicate:
            raise
        with engine.connect() as connection:
            user = linked_user(connection, uid)
        if user is not None:
            return dict(user)
        raise HTTPException(409, "Email already registered") from None


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
def register(request: RegisterRequest):
    if find_user_by_email(request.email) is not None:
        raise HTTPException(409, "Email already registered")
    identity = firebase_service.authenticate("signUp", request.email, request.password)
    user = sync_firebase_user(identity)
    return RegisterResponse(**user, message="Registration successful")


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    identity = firebase_service.authenticate(
        "signInWithPassword", request.email, request.password
    )
    user = sync_firebase_user(identity)
    return LoginResponse(
        **user,
        message="Login successful",
        access_token=create_access_token(user["user_id"]),
        token_type="bearer",
    )


@router.post("/google", response_model=LoginResponse)
def google_login(request: GoogleLoginRequest):
    identity = firebase_service.authenticate_google(request.id_token)
    user = sync_firebase_user(identity)
    return LoginResponse(
        **user,
        message="Login successful",
        access_token=create_access_token(user["user_id"]),
        token_type="bearer",
    )


@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(request: PasswordResetRequest):
    firebase_service.send_password_reset_email(request.email)
    return PasswordResetResponse(
        message="If the email is registered, a password reset link will be sent."
    )


@router.get("/me")
def get_me(payload=Depends(get_token_payload)):
    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with engine.connect() as connection:
        user = (
            connection.execute(
                text("""
                SELECT u.id, u.email
                FROM users u
                JOIN user_firebase_accounts f ON f.user_id = u.id
                WHERE u.id = :user_id
            """),
                {"user_id": user_id},
            )
            .mappings()
            .first()
        )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user["id"],
        "email": user["email"],
    }
