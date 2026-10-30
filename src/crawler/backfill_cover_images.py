"""Bổ sung ảnh bìa bị thiếu: python -m src.crawler.backfill_cover_images."""

import sys
import time
from bs4 import BeautifulSoup
from sqlalchemy import text
from src.crawler.vnexpress_crawler import get_cover_image, get_soup
from src.db.db import engine

MISSING = "(image_url IS NULL OR TRIM(image_url) = '')"


def backfill_cover_images():
    with engine.connect() as connection:
        articles = (
            connection.execute(
                text("SELECT id, url, content_html FROM articles WHERE " + MISSING)
            )
            .mappings()
            .all()
        )

    counts = {"updated": 0, "no_image": 0, "failed": 0}
    for article in articles:
        try:
            soup = BeautifulSoup(article["content_html"] or "", "html.parser")
            image_url = get_cover_image(soup, article["url"])
            if not image_url:
                time.sleep(0.3)
                image_url = get_cover_image(get_soup(article["url"]), article["url"])
            if not image_url:
                counts["no_image"] += 1
                continue

            with engine.begin() as connection:
                result = connection.execute(
                    text(
                        "UPDATE articles SET image_url = :image_url WHERE id = :id AND "
                        + MISSING
                    ),
                    {"image_url": image_url, "id": article["id"]},
                )
            counts["updated"] += result.rowcount
        except Exception as exc:
            counts["failed"] += 1
            print(f'ID {article["id"]}: {type(exc).__name__}', flush=True)

    print(counts, flush=True)
    return counts


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    counts = backfill_cover_images()
    raise SystemExit(1 if counts["failed"] else 0)
