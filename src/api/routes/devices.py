from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from src.api.routes.auth import get_me
from src.api.schemas import DeviceTokenRequest
from src.db.db import engine

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.post("")
def save_device_token(request: DeviceTokenRequest, user=Depends(get_me)):
    token = request.fcm_token.strip()

    if not token or not token.isascii():
        raise HTTPException(status_code=422, detail="FCM token is invalid")

    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO user_devices (user_id, fcm_token)
                VALUES (:user_id, :fcm_token)
                ON DUPLICATE KEY UPDATE user_id = :user_id
            """),
            {"user_id": user["user_id"], "fcm_token": token},
        )

    return {"message": "Device token saved successfully"}


@router.post("/remove")
def remove_device_token(request: DeviceTokenRequest, user=Depends(get_me)):
    token = request.fcm_token.strip()

    if not token or not token.isascii():
        raise HTTPException(status_code=422, detail="FCM token is invalid")

    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM user_devices
                WHERE user_id = :user_id
                  AND fcm_token = :fcm_token
            """),
            {"user_id": user["user_id"], "fcm_token": token},
        )

    return {"message": "Device token removed successfully"}
