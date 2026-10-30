"""Bổ sung chủ đề chính cho các bài đã crawl."""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import bindparam, inspect, text
from src.crawler.vnexpress_crawler import get_soup
from src.db.db import engine
from src.news_topics import MAIN_TOPICS, get_main_category

MISSING = "(main_category IS NULL OR TRIM(main_category) = '')"


def ensure_main_category_column():
    columns = {column["name"] for column in inspect(engine).get_columns("articles")}
    if "main_category" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE articles ADD COLUMN main_category VARCHAR(100) NULL")
            )


def update_main_category(article):
    try:
        time.sleep(0.3)
        topic = get_main_category(get_soup(article["url"]))
        if topic is None:
            return "skipped", article["id"]
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE articles SET main_category = :topic WHERE id = :id AND "
                    + MISSING
                ),
                {"topic": topic, "id": article["id"]},
            )
        return ("updated" if result.rowcount else "skipped"), article["id"]
    except Exception as exc:
        print(f'ID {article["id"]}: {type(exc).__name__}', flush=True)
        return "failed", article["id"]


def backfill_main_category(workers=3):
    ensure_main_category_column()
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "UPDATE articles SET main_category = category WHERE "
                + MISSING
                + " AND category IN :topics"
            ).bindparams(bindparam("topics", expanding=True)),
            {"topics": MAIN_TOPICS},
        )
        copied = result.rowcount
        rows = (
            connection.execute(
                text(
                    "SELECT id, url FROM articles WHERE "
                    + MISSING
                    + " ORDER BY id DESC"
                )
            )
            .mappings()
            .all()
        )
    counts = {"updated": copied, "skipped": 0, "failed": 0}
    print(
        f"Đã nhận diện {copied} bài; cần đọc chuyên mục của {len(rows)} bài.",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for start in range(0, len(rows), workers):
            for status, article_id in executor.map(
                update_main_category, rows[start : start + workers]
            ):
                counts[status] += 1
            done = min(start + workers, len(rows))
            if done % 30 == 0 or done == len(rows):
                print(f"[{done}/{len(rows)}] {counts}", flush=True)
    return counts


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Bổ sung chủ đề chính cho bài cũ.")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    counts = backfill_main_category(args.workers)
    print(f"Hoàn tất: {counts}", flush=True)
    return 1 if counts["skipped"] or counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
