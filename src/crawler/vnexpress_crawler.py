import argparse
import sys
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

from src.crawler.rss_common import run_rss_crawler
from src.news_topics import CRAWL_CATEGORIES, get_main_category

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

CATEGORIES = CRAWL_CATEGORIES
RSS_FEEDS = {
    "Thời sự": "thoi-su",
    "Thế giới": "the-gioi",
    "Kinh doanh": "kinh-doanh",
    "Khoa học": "khoa-hoc-cong-nghe",
    "Thể thao": "the-thao",
    "Giải trí": "giai-tri",
    "Sức khỏe": "suc-khoe",
    "Công nghệ": "khoa-hoc-cong-nghe",
    "Giáo dục": "giao-duc",
    "Pháp luật": "phap-luat",
    "Du lịch": "du-lich",
    "Đời sống": "gia-dinh",
    "Xe": "oto-xe-may",
    "Bất động sản": "bat-dong-san",
}
VIETNAM_TZ = timezone(timedelta(hours=7))


def get_soup(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def parse_published_at(date_text):
    if not date_text:
        return None

    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4}),\s*(\d{1,2}):(\d{2})", date_text)
    if match:
        day, month, year, hour, minute = map(int, match.groups())
        return datetime(year, month, day, hour, minute)

    try:
        result = parsedate_to_datetime(date_text.strip())
    except (TypeError, ValueError, OverflowError):
        return None
    if result.tzinfo is not None:
        result = result.astimezone(VIETNAM_TZ).replace(tzinfo=None)
    return result


def canonical_article_url(value):
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "vnexpress.net", "www.vnexpress.net"
        ):
            return None
        return "https://vnexpress.net" + parsed.path
    except ValueError:
        return None


def get_content_html(soup, url):
    body = soup.select_one("article.fck_detail")

    if body is None:
        return ""

    for node in body.select("script, style, iframe, noscript"):
        node.decompose()

    for element in body.select("img, picture source"):
        lazy_src = element.get("data-src") or element.get("data-original")

        src = lazy_src or element.get("src")

        if src:
            element["src"] = urljoin(url, src)

        lazy_srcset = element.get("data-srcset")

        if lazy_srcset:
            element["srcset"] = lazy_srcset
        elif lazy_src:
            element.attrs.pop("srcset", None)

        element.attrs.pop("loading", None)

    for element in body.find_all(True):
        for attribute in list(element.attrs):
            if attribute.lower().startswith("on"):
                del element[attribute]

    return body.decode_contents()


def get_cover_image(soup, url):
    """Ưu tiên ảnh bìa của báo, thiếu thì lấy ảnh đầu trong nội dung."""
    candidates = []
    for selector in (
        'meta[property="og:image"]',
        'meta[name="og:image"]',
        'meta[name="twitter:image"]',
        'meta[property="twitter:image"]',
    ):
        tag = soup.select_one(selector)
        if tag:
            candidates.append(tag.get("content"))

    body = soup.select_one("article.fck_detail")
    for image in (body if body is not None else soup).select("img"):
        candidates.extend(
            [image.get("data-src"), image.get("data-original"), image.get("src")]
        )

    for candidate in candidates:
        if not candidate or not candidate.strip() or candidate.startswith("#"):
            continue
        image_url = urljoin(url, candidate.strip())
        if urlparse(image_url).scheme in ("http", "https"):
            return image_url
    return None


def get_article(url):
    soup = get_soup(url)

    image_url = get_cover_image(soup, url)

    title = soup.select_one("h1.title-detail")

    description = soup.select_one("p.description")

    paragraphs = []

    for p in soup.select("article.fck_detail p.Normal"):
        text_content = p.get_text(" ", strip=True)

        if text_content and text_content not in paragraphs:
            paragraphs.append(text_content)

    breadcrumb = soup.select_one("ul.breadcrumb")

    category = ""

    if breadcrumb:
        links = breadcrumb.select("a")

        if links:
            category = links[-1].get_text(" ", strip=True)

    date = soup.select_one("span.date")

    date_text = date.get_text(" ", strip=True) if date else ""

    published_at = parse_published_at(date_text)

    return {
        "title": (title.get_text(" ", strip=True) if title else ""),
        "description": (description.get_text(" ", strip=True) if description else ""),
        "content": "\n".join(paragraphs),
        "content_html": get_content_html(soup, url),
        "category": category,
        "main_category": get_main_category(soup),
        "url": url,
        "image_url": image_url,
        "published_at": published_at,
    }


def main(categories=None, days=2, limit_per_category=10):
    """Lấy RSS VnExpress rồi chuyển việc xử lý chung cho bộ crawl RSS."""
    return run_rss_crawler(
        source_name="VnExpress",
        feed_paths=RSS_FEEDS,
        feed_url=lambda topic, path: f"https://vnexpress.net/rss/{path}.rss",
        canonicalize_url=canonical_article_url,
        parse_date=parse_published_at,
        get_article=lambda url, topic: get_article(url),
        categories=categories,
        days=days,
        limit_per_category=limit_per_category,
        require_topic_match=True,
        require_main_category=False,
        headers=HEADERS,
        article_delay=0.5,
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Thu thập tin từ RSS VnExpress.")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=list(CATEGORIES),
        help="Các chủ đề cần crawl; mặc định là tất cả.",
    )
    parser.add_argument(
        "--days", type=int, default=2,
        help="Lấy bài trong N ngày gần đây.",
    )
    parser.add_argument("--limit-per-category", type=int, default=10)
    args = parser.parse_args()
    if args.days < 1 or args.limit_per_category < 1:
        parser.error("--days và --limit-per-category phải lớn hơn 0")
    main(args.categories, args.days, args.limit_per_category)
