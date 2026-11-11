import time

from src.crawler.vnexpress_crawler import main as crawl_vnexpress
from src.crawler.dantri_crawler import main as crawl_dantri
from src.crawler.tuoitre_crawler import main as crawl_tuoitre
from src.crawler.vietnamnet_crawler import main as crawl_vietnamnet
from src.embedding.generate_embeddings import main as generate_embeddings
from src.notifications.service import notify_new_articles
from src.db.admin_store import init_admin_tables, get_sources, source_started, source_finished

UPDATE_INTERVAL_SECONDS = 5 * 60


def main(sources=None):
    """Shared by n8n, the admin page and the existing CLI."""
    init_admin_tables()
    crawlers = {"vnexpress": crawl_vnexpress, "dantri": crawl_dantri,
                "tuoitre": crawl_tuoitre, "vietnamnet": crawl_vietnamnet}
    selected = None if sources is None else set(sources)
    if selected is not None and not selected.issubset(crawlers):
        raise ValueError("Nguồn tin không hợp lệ")
    new_articles, results = [], []
    for source in get_sources():
        code = source["code"]
        if not source["enabled"] or (selected is not None and code not in selected):
            continue
        source_started(code)
        try:
            if code == "vnexpress":
                articles = crawlers[code](days=2, max_pages=1)
            elif code in ("tuoitre", "vietnamnet"):
                articles = crawlers[code](days=2, limit_per_category=5)
            else:
                articles = crawlers[code](days=2)
            new_articles.extend(articles)
        except Exception as exc:
            error = type(exc).__name__
            source_finished(code, error=error)
            results.append({"code": code, "status": "failed", "new_articles": 0, "error": error})
            print(f"Không cập nhật được {source['name']}: {error}")
        else:
            source_finished(code, count=len(articles))
            results.append({"code": code, "status": "finished", "new_articles": len(articles), "error": ""})
    if results:
        generate_embeddings()
        print(f"Có {len(new_articles)} bài mới vừa được lưu")
        notify_new_articles(new_articles)
    return {"status": "partial" if any(row["status"] == "failed" for row in results) else "finished",
            "new_articles": len(new_articles), "sources": results}


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print("Lỗi cập nhật tin:", exc)
        print(f"Chờ {UPDATE_INTERVAL_SECONDS // 60} phút để cập nhật tiếp...")
        time.sleep(UPDATE_INTERVAL_SECONDS)
