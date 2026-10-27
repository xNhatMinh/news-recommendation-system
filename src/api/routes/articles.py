from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from src.api.routes.auth import get_me
from src.api.schemas import LatestArticlesResponse
from src.db.db import engine
from src.news_topics import MAIN_TOPICS


router = APIRouter(
    prefix="/articles",
    tags=["Articles"]
)


@router.get("/latest", response_model=LatestArticlesResponse)
def get_latest_articles(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str | None = Query(None, min_length=1, max_length=100),
    user=Depends(get_me)
):
    sql = """
        SELECT title,
               COALESCE(description, '') AS description,
               COALESCE(NULLIF(main_category, ''), category) AS category,
               url, image_url, published_at
        FROM articles
        WHERE published_at IS NOT NULL
    """
    parameters = {"limit": limit + 1, "offset": offset}

    if category is not None:
        sql += " AND COALESCE(NULLIF(main_category, ''), category) = :category"
        parameters["category"] = category

    sql += " ORDER BY published_at DESC, id DESC LIMIT :limit OFFSET :offset"

    with engine.connect() as connection:
        rows = connection.execute(text(sql), parameters).mappings().all()

    return {
        "results": [dict(row) for row in rows[:limit]],
        "categories": MAIN_TOPICS,
        "has_more": len(rows) > limit
    }


@router.get("/detail")
def get_article_detail(
    url: str,
    user=Depends(get_me)
):
    with engine.connect() as connection:
        article = connection.execute(
            text("""
                SELECT
                    title,
                    description,
                    content,
                    content_html,
                    COALESCE(NULLIF(main_category, ''), category) AS category,
                    image_url,
                    published_at,
                    url
                FROM articles
                WHERE url = :url
                LIMIT 1
            """),
            {"url": url}
        ).mappings().first()

    if article is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy bài báo"
        )

    result = dict(article)
    result["description"] = result["description"] or ""
    result["content"] = result["content"] or ""
    result["content_html"] = result["content_html"] or ""

    return result