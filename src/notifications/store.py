from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.db.db import engine


def notification_counts(connection, user_id):
    row = (
        connection.execute(
            text("""
        SELECT COUNT(*) AS total_count,
               COALESCE(SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END), 0) AS unread_count
        FROM user_notifications WHERE user_id = :user_id
    """),
            {"user_id": user_id},
        )
        .mappings()
        .one()
    )
    return {
        "total_count": int(row["total_count"]),
        "unread_count": int(row["unread_count"]),
    }


def save_notification(user_id, article_url, topic):
    """Một tài khoản chỉ nhận một thông báo cho mỗi bài báo."""
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                INSERT INTO user_notifications (user_id, article_id, topic, is_read, created_at)
                SELECT :user_id, a.id, :topic, 0, :created_at
                FROM articles a
                WHERE a.url = :url
                  AND NOT EXISTS (
                      SELECT 1 FROM user_notifications n
                      WHERE n.user_id = :user_id AND n.article_id = a.id
                  )
            """),
                {
                    "user_id": user_id,
                    "url": article_url,
                    "topic": topic,
                    "created_at": datetime.now(timezone.utc).replace(
                        tzinfo=None, microsecond=0
                    ),
                },
            )
            return result.rowcount > 0
    except IntegrityError as exc:
        duplicate = exc.orig.args and exc.orig.args[0] == 1062
        duplicate = (
            duplicate
            or "UNIQUE constraint failed: user_notifications.user_id, user_notifications.article_id"
            in str(exc.orig)
        )
        if duplicate:
            return False
        raise
