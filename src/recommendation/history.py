from sqlalchemy import text

from src.db.db import engine


def save_recommendation_history(
    user_id,
    articles
):
    sql = text("""
        INSERT INTO recommendation_history (
            user_id,
            article_id,
            score
        )
        SELECT
            :user_id,
            id,
            :score
        FROM articles
        WHERE url = :url
    """)

    with engine.begin() as connection:

        for article in articles:

            connection.execute(
                sql,
                {
                    "user_id": user_id,
                    "url": article["url"],
                    "score": article["personalized_score"]
                }
            )


def get_recommendation_history(user_id, limit=20):
    sql = text("""
        SELECT
            rh.id,
            rh.user_id,
            rh.article_id,
            a.title,
            a.url,
            rh.score,
            rh.created_at
        FROM recommendation_history rh
        JOIN articles a
            ON rh.article_id = a.id
        WHERE rh.user_id = :user_id
        ORDER BY rh.created_at DESC, rh.id DESC
        LIMIT :limit
    """)

    with engine.connect() as connection:
        rows = connection.execute(
            sql,
            {
                "user_id": user_id,
                "limit": limit
            }
        ).fetchall()

    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "article_id": row.article_id,
            "title": row.title,
            "url": row.url,
            "score": float(row.score),
            "created_at": row.created_at
        }
        for row in rows
    ]