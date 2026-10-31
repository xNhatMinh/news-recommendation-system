from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.routes.auth import get_me
from src.api.schemas import BookmarkRequest, BookmarkStatus, SavedArticlesResponse
from src.db.db import engine

router = APIRouter(prefix="/bookmarks", tags=["Bookmarks"])


@router.get("", response_model=SavedArticlesResponse)
def get_bookmarks(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_me),
):
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text("""
            SELECT a.title, COALESCE(a.description, '') AS description,
                   COALESCE(NULLIF(a.main_category, ''), a.category) AS category,
                   a.url, a.image_url, a.published_at
            FROM user_bookmarks b
            JOIN articles a ON a.id = b.article_id
            WHERE b.user_id = :user_id
            ORDER BY b.id DESC
            LIMIT :limit OFFSET :offset
        """),
                {"user_id": user["user_id"], "limit": limit + 1, "offset": offset},
            )
            .mappings()
            .all()
        )
    return {
        "results": [dict(row) for row in rows[:limit]],
        "has_more": len(rows) > limit,
    }


@router.get("/status", response_model=BookmarkStatus)
def get_bookmark_status(
    url: str = Query(..., min_length=1, max_length=2048),
    user=Depends(get_me),
):
    with engine.connect() as connection:
        saved = connection.execute(
            text("""
            SELECT b.id FROM user_bookmarks b
            JOIN articles a ON a.id = b.article_id
            WHERE b.user_id = :user_id AND a.url = :url
            LIMIT 1
        """),
            {"user_id": user["user_id"], "url": url},
        ).first()
    return {"is_saved": saved is not None}


@router.put("", response_model=BookmarkStatus)
def save_bookmark(request: BookmarkRequest, user=Depends(get_me)):
    try:
        with engine.begin() as connection:
            article_id = connection.execute(
                text("SELECT id FROM articles WHERE url = :url LIMIT 1"),
                {"url": request.url},
            ).scalar()
            if article_id is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy bài báo")

            connection.execute(
                text("""
                INSERT INTO user_bookmarks (user_id, article_id, created_at)
                SELECT :user_id, :article_id, :created_at
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_bookmarks
                    WHERE user_id = :user_id AND article_id = :article_id
                )
            """),
                {
                    "user_id": user["user_id"],
                    "article_id": article_id,
                    "created_at": datetime.now(timezone.utc).replace(
                        tzinfo=None, microsecond=0
                    ),
                },
            )
    except IntegrityError as exc:
        # Hai yêu cầu lưu đồng thời vẫn chỉ tạo một bản ghi.
        duplicate = exc.orig.args and exc.orig.args[0] == 1062
        duplicate = (
            duplicate
            or "UNIQUE constraint failed: user_bookmarks.user_id, user_bookmarks.article_id"
            in str(exc.orig)
        )
        if not duplicate:
            raise
    return {"is_saved": True}


@router.delete("", response_model=BookmarkStatus)
def remove_bookmark(
    url: str = Query(..., min_length=1, max_length=2048),
    user=Depends(get_me),
):
    with engine.begin() as connection:
        connection.execute(
            text("""
            DELETE FROM user_bookmarks
            WHERE user_id = :user_id
              AND article_id IN (SELECT id FROM articles WHERE url = :url)
        """),
            {"user_id": user["user_id"], "url": url},
        )
    return {"is_saved": False}
