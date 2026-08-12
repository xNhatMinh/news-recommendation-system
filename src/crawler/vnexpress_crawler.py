import requests
from bs4 import BeautifulSoup
import json
import time


URL = "https://vnexpress.net/thoi-su"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_soup(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=10
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def get_article_urls(limit=10):
    soup = get_soup(URL)

    urls = []

    for article in soup.select("article.item-news"):
        link = article.select_one("h3.title-news a")

        if link:
            url = link.get("href")

            if url and url not in urls:
                urls.append(url)

        if len(urls) >= limit:
            break

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

    print("Collecting article URLs...")

    urls = get_article_urls(10)

    print(f"Found {len(urls)} article URLs")

    articles = []

    for i, url in enumerate(urls, 1):

        print(f"[{i}/{len(urls)}] Crawling...")

        try:
            article = get_article(url)

            if article["title"] and article["content"]:
                articles.append(article)
                print(f"-> {article['title']}")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(1)

    with open(
    r"C:\news-ai-agent\data\articles.json",
    "w",
    encoding="utf-8"
    ) as f:

        json.dump(
            articles,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"\nSaved {len(articles)} articles")


if __name__ == "__main__":
    main()