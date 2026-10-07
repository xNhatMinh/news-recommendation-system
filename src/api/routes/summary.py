from datetime import date

from fastapi import APIRouter
from sqlalchemy import text

from src.db.db import engine


router = APIRouter(
    prefix="/summary",
    tags=["Summary"]
)


@router.get("/{user_id}")
def get_summary(
    user_id: int,
    start_date: date,
    end_date: date
):
    sql = text("""
        SELECT
            id,
            user_id,
            topic,
            start_date,
            end_date,
            summary,
            created_at
        FROM summaries
        WHERE user_id = :user_id
          AND start_date = :start_date
          AND end_date = :end_date
        ORDER BY created_at DESC
        LIMIT 1
    """)

    with engine.connect() as connection:
        row = connection.execute(
            sql,
            {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date
            }
        ).fetchone()

    if row is None:
        return {
            "message": "Summary not found"
        }

    return {
        "id": row.id,
        "user_id": row.user_id,
        "topic": row.topic,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "summary": row.summary,
        "created_at": row.created_at
    }