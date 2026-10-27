"""Bo sung HTML cho bai cu: python -m src.crawler.backfill_article_html."""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from sqlalchemy import text

from src.crawler.vnexpress_crawler import get_content_html, get_soup
from src.db.db import engine


def update_article_html(article):
    try:
        time.sleep(0.5)
        soup = get_soup(article["url"])
        content_html = get_content_html(soup, article["url"])

        if not content_html.strip():
            return "skipped", f'ID {article["id"]}: không tìm thấy nội dung'

        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    UPDATE articles
                    SET content_html = :content_html
                    WHERE id = :article_id
                      AND (content_html IS NULL OR TRIM(content_html) = '')
                """),
                {
                    "article_id": article["id"],
                    "content_html": content_html,
                },
            )

        if result.rowcount == 0:
            return "skipped", f'ID {article["id"]}: đã được cập nhật'

        image_count = len(BeautifulSoup(content_html, "html.parser").select("img"))
        return "updated", f'ID {article["id"]}: {image_count} ảnh'
    except Exception as exc:
        return "failed", f'ID {article["id"]}: {type(exc).__name__}'


def backfill_article_html(limit=None, url=None, workers=3):
    if limit is not None and limit < 1:
        raise ValueError("limit phải lớn hơn 0")
    if not 1 <= workers <= 4:
        raise ValueError("workers phải từ 1 đến 4")

    sql = """
        SELECT id, url
        FROM articles
        WHERE (content_html IS NULL OR TRIM(content_html) = '')
    """
    parameters = {}

    if url:
        sql += " AND url = :url"
        parameters["url"] = url

    sql += " ORDER BY published_at DESC, id DESC"

    if limit is not None:
        sql += " LIMIT :limit"
        parameters["limit"] = limit

    with engine.connect() as connection:
        articles = connection.execute(text(sql), parameters).mappings().all()

    total = len(articles)
    counts = {"updated": 0, "skipped": 0, "failed": 0}
    print(f"Có {total} bài cần bổ sung HTML.", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Chỉ đưa vào nhóm nhỏ để có thể dừng mà không chờ toàn bộ danh sách.
        for start in range(0, total, workers):
            batch = articles[start:start + workers]
            for status, message in executor.map(update_article_html, batch):
                counts[status] += 1
                completed = sum(counts.values())
                if status != "updated" or completed % 25 == 0 or completed == total:
                    print(
                        f'[{completed}/{total}] Đã cập nhật: {counts["updated"]} '
                        f'| Bỏ qua: {counts["skipped"]} | Lỗi: {counts["failed"]} '
                        f'| {message}',
                        flush=True,
                    )

    print(
        f'Hoàn tất: {counts["updated"]} bài đã cập nhật, '
        f'{counts["skipped"]} bài bỏ qua, {counts["failed"]} bài lỗi.',
        flush=True,
    )
    return counts


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Bổ sung HTML và ảnh cho bài báo cũ.")
    parser.add_argument("--limit", type=int, help="Số bài tối đa, mặc định là tất cả.")
    parser.add_argument("--url", help="Chỉ cập nhật bài có URL này.")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit phải lớn hơn 0")

    counts = backfill_article_html(args.limit, args.url, args.workers)
    return 1 if counts["failed"] or counts["skipped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
