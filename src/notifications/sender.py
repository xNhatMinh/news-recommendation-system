from firebase_admin import messaging

from src.notifications.firebase_config import firebase_app
from sqlalchemy import text
from src.db.db import engine


def send_notification(fcm_token: str, title: str, body: str, data=None):
    message = messaging.Message(
        token=fcm_token,
        data=data or {},
        notification=messaging.Notification(title=title, body=body),
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(channel_id="news_alerts"),
        ),
    )

    return messaging.send(message, app=firebase_app)


def send_notification_to_user(user_id: int, title: str, body: str, data=None):
    with engine.connect() as connection:
        tokens = (
            connection.execute(
                text("""
                SELECT fcm_token
                FROM user_devices
                WHERE user_id = :user_id
            """),
                {"user_id": user_id},
            )
            .scalars()
            .all()
        )

    sent_count = 0

    for token in tokens:
        try:
            send_notification(token, title, body, data=data)
            sent_count += 1

        except messaging.UnregisteredError:
            print("Token không còn sử dụng được, đang xóa liên kết")

            with engine.begin() as connection:
                connection.execute(
                    text("""
                        DELETE FROM user_devices
                        WHERE user_id = :user_id
                          AND fcm_token = :fcm_token
                    """),
                    {"user_id": user_id, "fcm_token": token},
                )

        except Exception as e:
            print(f"Lỗi gửi đến một thiết bị của user {user_id}: {e}")

    return sent_count
