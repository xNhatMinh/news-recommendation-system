import requests
from bs4 import BeautifulSoup
import json
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
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
        timeout=10
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "lxml"
    )

def get_page_url(category_url, page):
    if page == 1:
        return category_url

    return category_url + f"-p{page}"


def get_article_urls(category_url, pages=5, limit_per_page=30):

    urls = []

    for page in range(1, pages + 1):

        page_url = get_page_url(
            category_url,
            page
        )

        print(f"   Page {page}: {page_url}")

        try:
            soup = get_soup(page_url)

            count = 0

            for article in soup.select("article.item-news"):

                link = article.select_one(
                    "h3.title-news a"
                )

                if link:

                    url = link.get("href")

                    if url and url not in urls:
                        urls.append(url)
                        count += 1

                if count >= limit_per_page:
                    break

            print(
                f"   -> Found {count} URLs"
            )

        except Exception as e:

            print(
                f"   -> Error page {page}: {e}"
            )

        time.sleep(1)

    return urls

def get_article(url):
    soup = get_soup(url)

    title = soup.select_one("h1.title-detail")
    description = soup.select_one("p.description")

    paragraphs = []

    for p in soup.select("article.fck_detail p.Normal"):
        text = p.get_text(" ", strip=True)

        if text and text not in paragraphs:
            paragraphs.append(text)

    breadcrumb = soup.select_one("ul.breadcrumb")
    category = ""

    if breadcrumb:
        links = breadcrumb.select("a")

        if links:
            category = links[-1].get_text(
                " ",
                strip=True
            )

    date = soup.select_one("span.date")

    return {
        "title": title.get_text(" ", strip=True) if title else "",
        "description": description.get_text(" ", strip=True) if description else "",
        "content": "\n".join(paragraphs),
        "category": category,
        "url": url,
        "published_at": date.get_text(" ", strip=True) if date else ""
    }


def main():
    print("Starting crawler...\n")

    all_urls = []

    for category_name, category_url in CATEGORIES.items():
        print(f"Collecting: {category_name}")

        try:
            urls = get_article_urls(
                category_url,
                pages=5,
                limit_per_page=30
            )

            print(f"-> Found {len(urls)} URLs")

            for url in urls:
                if url not in all_urls:
                    all_urls.append(url)

        except Exception as e:
            print(f"Error collecting {category_name}: {e}")

        time.sleep(1)

    print(f"\nTotal unique URLs: {len(all_urls)}")

    articles = []

    for i, url in enumerate(all_urls, 1):
        print(f"[{i}/{len(all_urls)}] Crawling...")

        try:
            article = get_article(url)

            if (
                article["title"]
                and article["description"]
                and article["content"]
            ):
                articles.append(article)
                print(f"-> {article['title']}")
            else:
                print("-> Skip: missing data")

        except Exception as e:
            print(f"-> Error: {e}")

        time.sleep(1)

    unique_articles = []
    seen_urls = set()

    for article in articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            unique_articles.append(article)

    output_file = DATA_DIR / "articles.json"

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            unique_articles,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"\nSaved {len(unique_articles)} articles")
    print(f"File: {output_file}")


if __name__ == "__main__":
    main()