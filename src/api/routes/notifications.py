from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from src.api.routes.auth import get_me
from src.api.schemas import NotificationCounts, NotificationsResponse
from src.db.db import engine
from src.notifications.store import notification_counts

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationsResponse)
def get_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
    user=Depends(get_me),
):
    sql = """
        SELECT n.id, n.topic, n.is_read, n.created_at,
               a.title, COALESCE(a.description, '') AS description, a.url, a.image_url
        FROM user_notifications n JOIN articles a ON n.article_id = a.id
        WHERE n.user_id = :user_id
    """
    if unread_only:
        sql += " AND n.is_read = 0"
    sql += " ORDER BY n.id DESC LIMIT :limit OFFSET :offset"
    with engine.connect() as connection:
        counts = notification_counts(connection, user["user_id"])
        rows = (
            connection.execute(
                text(sql),
                {
                    "user_id": user["user_id"],
                    "limit": limit + 1,
                    "offset": offset,
                },
            )
            .mappings()
            .all()
        )
    return {
        **counts,
        "results": [dict(row) for row in rows[:limit]],
        "has_more": len(rows) > limit,
    }


@router.get("/unread-count", response_model=NotificationCounts)
def get_unread_count(user=Depends(get_me)):
    with engine.connect() as connection:
        return notification_counts(connection, user["user_id"])


@router.patch("/read-all", response_model=NotificationCounts)
def read_all_notifications(user=Depends(get_me)):
    with engine.begin() as connection:
        connection.execute(
            text("""
            UPDATE user_notifications SET is_read = 1
            WHERE user_id = :user_id AND is_read = 0
        """),
            {"user_id": user["user_id"]},
        )
        return notification_counts(connection, user["user_id"])


@router.patch("/{notification_id}/read", response_model=NotificationCounts)
def read_notification(notification_id: int, user=Depends(get_me)):
    with engine.begin() as connection:
        exists = connection.execute(
            text("""
            SELECT id FROM user_notifications WHERE id = :id AND user_id = :user_id
        """),
            {"id": notification_id, "user_id": user["user_id"]},
        ).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy thông báo")
        connection.execute(
            text("""
            UPDATE user_notifications SET is_read = 1
            WHERE id = :id AND user_id = :user_id
        """),
            {"id": notification_id, "user_id": user["user_id"]},
        )
        return notification_counts(connection, user["user_id"])
