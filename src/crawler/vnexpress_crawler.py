import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime

from sqlalchemy import text

from src.db.db import engine


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

CATEGORIES = {
    "Thời sự": "https://vnexpress.net/thoi-su",
    "Thế giới": "https://vnexpress.net/the-gioi",
    "Kinh doanh": "https://vnexpress.net/kinh-doanh",
    "Khoa học": "https://vnexpress.net/khoa-hoc",
    "Thể thao": "https://vnexpress.net/the-thao",
    "Giải trí": "https://vnexpress.net/giai-tri",
    "Sức khỏe": "https://vnexpress.net/suc-khoe"
}


def get_soup(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def get_page_url(category_url, page):
    if page == 1:
        return category_url

    return f"{category_url}-p{page}"


def parse_published_at(date_text):
    if not date_text:
        return None

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}):(\d{2})",
        date_text
    )

    if not match:
        return None

    day, month, year, hour, minute = map(
        int,
        match.groups()
    )

    return datetime(
        year,
        month,
        day,
        hour,
        minute
    )


def get_latest_article_date():
    sql = text("""
        SELECT MAX(published_at)
        FROM articles
    """)

    with engine.connect() as connection:
        result = connection.execute(sql).scalar()

    return result


def get_article_urls(
    category_url,
    latest_date,
    max_pages=100,
    limit_per_page=30
):
    urls = []

    for page in range(1, max_pages + 1):
        page_url = get_page_url(
            category_url,
            page
        )

        print(f"   Page {page}: {page_url}")

        try:
            soup = get_soup(page_url)
        except Exception as e:
            print(f"   -> Error: {e}")
            break

        page_urls = []

        for article in soup.select("article.item-news"):
            link = article.select_one(
                "h3.title-news a"
            )

            if not link:
                continue

            url = link.get("href")

            if (
                url
                and url.startswith("https://vnexpress.net/")
                and url not in urls
                and url not in page_urls
            ):
                page_urls.append(url)

            if len(page_urls) >= limit_per_page:
                break

        if not page_urls:
            print("   -> Không còn bài")
            break

        urls.extend(page_urls)

        print(
            f"   -> Found {len(page_urls)} URLs"
        )

        if page >= 2:
            old_count = 0

            for url in page_urls:
                try:
                    article = get_article(url)

                    if (
                        article["published_at"]
                        and article["published_at"] <= latest_date
                    ):
                        old_count += 1

                except Exception:
                    continue

            if old_count == len(page_urls):
                print(
                    "   -> Đã đi qua dữ liệu cũ"
                )
                break

        time.sleep(0.5)

    return urls


def get_article(url):
    soup = get_soup(url)

    image_tag = soup.find("meta", property="og:image")

    image_url = None

    if image_tag:
        image_url = image_tag.get("content")

    title = soup.select_one(
        "h1.title-detail"
    )

    description = soup.select_one(
        "p.description"
    )

    paragraphs = []

    for p in soup.select(
        "article.fck_detail p.Normal"
    ):
        text_content = p.get_text(
            " ",
            strip=True
        )

        if (
            text_content
            and text_content not in paragraphs
        ):
            paragraphs.append(text_content)

    breadcrumb = soup.select_one(
        "ul.breadcrumb"
    )

    category = ""

    if breadcrumb:
        links = breadcrumb.select("a")

        if links:
            category = links[-1].get_text(
                " ",
                strip=True
            )

    date = soup.select_one(
        "span.date"
    )

    date_text = (
        date.get_text(
            " ",
            strip=True
        )
        if date
        else ""
    )

    published_at = parse_published_at(
        date_text
    )

    return {
        "title": (
            title.get_text(
                " ",
                strip=True
            )
            if title
            else ""
        ),
        "description": (
            description.get_text(
                " ",
                strip=True
            )
            if description
            else ""
        ),
        "content": "\n".join(paragraphs),
        "category": category,
        "url": url,
        "image_url": image_url,
        "published_at": published_at
    }


def article_exists(connection, url):
    sql = text("""
        SELECT id
        FROM articles
        WHERE url = :url
        LIMIT 1
    """)

    result = connection.execute(
        sql,
        {"url": url}
    ).fetchone()

    return result is not None


def insert_article(connection, article):
    sql = text("""
        INSERT INTO articles (
            title,
            description,
            content,
            category,
            url,
            image_url,
            published_at
        )
        VALUES (
            :title,
            :description,
            :content,
            :category,
            :url,
            :image_url,
            :published_at
        )
    """)

    connection.execute(
        sql,
        {
            "title": article["title"],
            "description": article["description"],
            "content": article["content"],
            "category": article["category"],
            "url": article["url"],
            "image_url": article.get("image_url"),
            "published_at": article["published_at"]
        }
    )


def main():
    print("=" * 60)
    print("VNEXPRESS INCREMENTAL CRAWLER")
    print("=" * 60)

    latest_date = get_latest_article_date()

    if latest_date:
        print(
            f"Dữ liệu mới nhất trong DB: "
            f"{latest_date}"
        )
    else:
        print(
            "Database chưa có dữ liệu."
        )
        latest_date = datetime.min

    current_date = datetime.now()

    print(
        f"Ngày hiện tại: {current_date}"
    )

    all_urls = []

    for category_name, category_url in CATEGORIES.items():
        print(
            f"\nCollecting: {category_name}"
        )

        try:
            urls = get_article_urls(
                category_url,
                latest_date
            )

            print(
                f"-> Found {len(urls)} URLs"
            )

            for url in urls:
                if url not in all_urls:
                    all_urls.append(url)

        except Exception as e:
            print(
                f"-> Error: {e}"
            )

        time.sleep(0.5)

    print(
        f"\nTotal unique URLs: "
        f"{len(all_urls)}"
    )

    new_articles = []

    for i, url in enumerate(
        all_urls,
        1
    ):
        print(
            f"[{i}/{len(all_urls)}] Crawling..."
        )

        try:
            article = get_article(url)

            published_at = article[
                "published_at"
            ]

            if not published_at:
                print(
                    "-> Skip: không có ngày đăng"
                )
                continue

            if published_at <= latest_date:
                print(
                    "-> Skip: bài cũ"
                )
                continue

            if published_at > current_date:
                print(
                    "-> Skip: ngày không hợp lệ"
                )
                continue

            if not article["title"]:
                print(
                    "-> Skip: thiếu tiêu đề"
                )
                continue

            if not article["content"]:
                print(
                    "-> Skip: thiếu nội dung"
                )
                continue

            new_articles.append(article)

            print(
                f"-> NEW: "
                f"{article['title']}"
            )

        except Exception as e:
            print(
                f"-> Error: {e}"
            )

        time.sleep(0.2)

    print(
        f"\nNew articles: "
        f"{len(new_articles)}"
    )

    inserted = 0
    skipped = 0

    print("\n" + "=" * 60)
    print("INSERT INTO MYSQL")
    print("=" * 60)

    with engine.begin() as connection:

        for article in new_articles:

            if article_exists(
                connection,
                article["url"]
            ):
                skipped += 1

                print(
                    f"SKIP: "
                    f"{article['title']}"
                )

                continue

            insert_article(
                connection,
                article
            )

            inserted += 1

            print(
                f"INSERT: "
                f"{article['title']}"
            )

    print("\n" + "=" * 60)
    print("CRAWLER FINISHED")
    print("=" * 60)

    print(
        f"URLs đã crawl: {len(all_urls)}"
    )

    print(
        f"Bài mới: {len(new_articles)}"
    )

    print(
        f"INSERT vào MySQL: {inserted}"
    )

    print(
        f"Đã tồn tại: {skipped}"
    )


if __name__ == "__main__":
    main()