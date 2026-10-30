from uuid import uuid4

from fastapi import APIRouter, HTTPException, status, Depends
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.schemas import RegisterRequest, RegisterResponse
from src.api.schemas import LoginRequest, LoginResponse
from src.db.db import engine
from src.api.security import create_access_token, get_token_payload

router = APIRouter(prefix="/auth", tags=["Auth"])
password_hash = PasswordHash.recommended()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(request: RegisterRequest):
    # Keep the required username independent of the email's length and format.
    username = f"user_{uuid4().hex}"
    hashed_password = password_hash.hash(request.password)

    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO users (username, email, password_hash)
                    VALUES (:username, :email, :password_hash)
                """),
                {
                    "username": username,
                    "email": request.email,
                    "password_hash": hashed_password,
                },
            )
            user_id = result.lastrowid
    except IntegrityError as exc:
        # Handle the database constraint, including simultaneous registrations.
        if (
            exc.orig.args
            and exc.orig.args[0] == 1062
            and "uq_users_email" in str(exc.orig)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from None
        raise

    return RegisterResponse(
        user_id=user_id,
        email=request.email,
        message="Registration successful",
    )


def find_user_by_email(email: str):
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT id, email, password_hash
                FROM users
                WHERE email = :email
            """),
            {"email": email},
        )

        return result.mappings().first()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    user = find_user_by_email(request.email)

    if (
        user is None
        or not user["password_hash"]
        or not password_hash.verify(
            request.password,
            user["password_hash"],
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
        )

    token = create_access_token(user["id"])

    return LoginResponse(
        user_id=user["id"],
        email=user["email"],
        message="Login successful",
        access_token=token,
        token_type="bearer",
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
                SELECT id, email
                FROM users
                WHERE id = :user_id
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
