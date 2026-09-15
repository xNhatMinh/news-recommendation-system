import json
import re
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

from src.db.db import engine


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "articles.json"


def parse_published_at(date_text):
    """
    Chuyển:
    Chủ nhật, 23/8/2026, 09:48 (GMT+7)

    thành:
    2026-08-23 09:48:00
    """

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}):(\d{2})",
        date_text
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))

    return datetime(
        year,
        month,
        day,
        hour,
        minute
    )


def import_articles():

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    sql = text("""
        INSERT INTO articles (
            title,
            description,
            content,
            category,
            url,
            published_at
        )
        VALUES (
            :title,
            :description,
            :content,
            :category,
            :url,
            :published_at
        )
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            description = VALUES(description),
            content = VALUES(content),
            category = VALUES(category),
            published_at = VALUES(published_at)
    """)

    success = 0

    with engine.begin() as connection:

        for article in articles:

            published_at = parse_published_at(
                article.get("published_at", "")
            )

            connection.execute(sql, {
                "title": article.get("title"),
                "description": article.get("description"),
                "content": article.get("content"),
                "category": article.get("category"),
                "url": article.get("url"),
                "published_at": published_at
            })

            success += 1

    print(f"Đã import {success} bài báo vào MySQL.")


if __name__ == "__main__":
    import_articles()