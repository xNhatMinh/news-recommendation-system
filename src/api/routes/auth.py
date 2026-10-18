from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.schemas import RegisterRequest, RegisterResponse
from src.db.db import engine


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
