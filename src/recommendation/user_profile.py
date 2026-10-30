from sqlalchemy import text

from src.db.db import engine


def get_user_preferences(user_id):

    sql = text("""
        SELECT topic, weight
        FROM user_preferences
        WHERE user_id = :user_id
        ORDER BY weight DESC
    """)

    with engine.connect() as connection:
        rows = connection.execute(sql, {"user_id": user_id}).fetchall()

    return [{"topic": row.topic, "weight": float(row.weight)} for row in rows]


def save_user_preferences(user_id, topics):
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM user_preferences
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        )

        for topic in topics:
            connection.execute(
                text("""
                    INSERT INTO user_preferences
                        (user_id, topic, weight)
                    VALUES
                        (:user_id, :topic, 1.0)
                """),
                {
                    "user_id": user_id,
                    "topic": topic,
                },
            )
