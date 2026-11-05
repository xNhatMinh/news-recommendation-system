import time

from src.crawler.vnexpress_crawler import main as crawl_vnexpress
from src.crawler.dantri_crawler import main as crawl_dantri
from src.embedding.generate_embeddings import main as generate_embeddings
from src.notifications.service import notify_new_articles

UPDATE_INTERVAL_SECONDS = 5 * 60


def main():
    """Crawl tin → tạo embedding → gửi thông báo phù hợp."""
    new_articles = []
    for name, crawl in (("VnExpress", crawl_vnexpress), ("Dân trí", crawl_dantri)):
        try:
            if name == "VnExpress":
                articles = crawl(days=2, max_pages=1)
            else:
                articles = crawl(days=2)
            new_articles.extend(articles)
        except Exception as exc:
            print(f"Không cập nhật được {name}: {type(exc).__name__}")
    generate_embeddings()
    print(f"Có {len(new_articles)} bài mới vừa được lưu")
    notify_new_articles(new_articles)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as exc:
            print("Lỗi cập nhật tin:", exc)
        print(f"Chờ {UPDATE_INTERVAL_SECONDS // 60} phút để cập nhật tiếp...")
        time.sleep(UPDATE_INTERVAL_SECONDS)
