from src.crawler.vnexpress_crawler import main as crawl_news
from src.embedding.generate_embeddings import main as generate_embeddings
import time
from src.notifications.service import notify_new_articles

def main():
    new_articles = crawl_news()
    generate_embeddings()

    print(f"Có {len(new_articles)} bài mới vừa được lưu")

    notify_new_articles(new_articles)


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("Lỗi cập nhật tin:", e)

        print("Chờ 1 giờ để cập nhật tiếp...")
        time.sleep(3600)