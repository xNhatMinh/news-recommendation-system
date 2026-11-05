"""Lấy tin từ RSS Dân trí và giữ nội dung, ảnh theo thứ tự bài gốc."""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.db.article_store import article_exists, insert_article
from src.db.db import engine
from src.news_topics import get_main_topic

FEED_PATHS = {
    "Thời sự": "thoi-su", "Thế giới": "the-gioi",
    "Kinh doanh": "kinh-doanh", "Khoa học": "khoa-hoc",
    "Thể thao": "the-thao", "Giải trí": "giai-tri",
    "Sức khỏe": "suc-khoe", "Công nghệ": "cong-nghe",
    "Giáo dục": "giao-duc", "Pháp luật": "phap-luat",
    "Du lịch": "du-lich", "Đời sống": "doi-song",
    "Xe": "o-to-xe-may", "Bất động sản": "bat-dong-san",
}
ROOT_TOPICS = {path: topic for topic, path in FEED_PATHS.items()}
ROOT_TOPICS.update({"xa-hoi": "Thời sự", "suc-manh-so": "Công nghệ"})
VIETNAM_TZ = timezone(timedelta(hours=7))
HEADERS = {"User-Agent": "Newsora/1.0 (academic news reader)"}
BODY_SELECTOR = '#articleContent [data-slot="content"], .singular-content'


def parse_published_at(value):
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value.strip())
        except (TypeError, ValueError, OverflowError):
            return None
    if date.tzinfo is not None:
        date = date.astimezone(VIETNAM_TZ).replace(tzinfo=None)
    return date


def get_feed_articles(feed_url):
    response = requests.get(feed_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "xml")
    articles = []
    seen = set()
    for item in soup.find_all("item"):
        link = item.find("link")
        if link is None:
            continue
        parsed = urlparse(link.get_text(strip=True))
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "dantri.com.vn", "www.dantri.com.vn"
        ):
            continue
        if not re.search(r"-\d{15,20}\.htm$", parsed.path):
            continue
        url = "https://dantri.com.vn" + parsed.path
        if url in seen:
            continue
        seen.add(url)
        date = item.find("pubDate")
        articles.append({
            "url": url,
            "published_at": parse_published_at(date.get_text() if date else ""),
        })
    return articles


def absolute_url(value, article_url):
    if not value or not value.strip() or value.strip().startswith("#"):
        return None
    url = urljoin(article_url, value.strip())
    return url if urlparse(url).scheme in ("http", "https") else None


def get_content_html(soup, url):
    original = soup.select_one(BODY_SELECTOR)
    if original is None:
        return ""
    body = BeautifulSoup(str(original), "html.parser").find()
    for node in body.select(
        'script, style, iframe, noscript, form, input, button, object, embed, '
        'video, audio, svg, [data-slot="ads-in-content"], '
        '.ads, .adsbygoogle, .related-news, .related-box, .content-box-related'
    ):
        node.decompose()

    for element in body.select("img, picture source"):
        src = absolute_url(
            element.get("data-src") or element.get("data-original") or element.get("src"), url
        )
        if src:
            element["src"] = src
        else:
            element.attrs.pop("src", None)
        srcset = element.get("data-srcset") or element.get("srcset") or ""
        candidates = []
        for candidate in srcset.split(","):
            parts = candidate.split()
            if parts and (image_url := absolute_url(parts[0], url)):
                candidates.append(" ".join([image_url, *parts[1:]]))
        if candidates:
            element["srcset"] = ", ".join(candidates)
        else:
            element.attrs.pop("srcset", None)

    allowed_tags = {
        "p", "div", "span", "figure", "figcaption", "picture", "source", "img",
        "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s", "a", "br",
        "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "td",
        "th", "sub", "sup",
    }
    for element in list(body.find_all(True)):
        if element.name not in allowed_tags:
            element.unwrap()
            continue
        element.attrs = {key: value for key, value in element.attrs.items()
                         if key in {"src", "srcset", "href", "alt", "title", "colspan", "rowspan"}}
        if element.has_attr("href"):
            href = absolute_url(element["href"], url)
            if href:
                element["href"] = href
            else:
                del element["href"]
    return body.decode_contents()


def get_article(url, default_category=None):
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "lxml")
    metadata = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text())
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") in ("NewsArticle", "Article"):
                metadata = item
                break
        if metadata:
            break

    title = soup.select_one('#articleContent h1, h1.title-page, h1')
    description = soup.select_one('[data-slot="sapo"], .singular-sapo, meta[name="description"]')
    image = soup.select_one('meta[property="og:image"]')
    date = soup.select_one("time[datetime]")
    content_html = get_content_html(soup, url)
    body = BeautifulSoup(content_html, "html.parser")
    sections = str(metadata.get("articleSection") or "").split(",")
    main_category = ROOT_TOPICS.get(urlparse(url).path.strip("/").split("/")[0])
    main_category = main_category or get_main_topic(sections[0]) or default_category
    first_image = body.select_one("img[src]")
    image_url = absolute_url(image.get("content"), url) if image else None

    return {
        "title": title.get_text(" ", strip=True) if title else metadata.get("headline", ""),
        "description": (description.get("content") or description.get_text(" ", strip=True))
                       if description else metadata.get("description", ""),
        "content": "\n".join(node.get_text(" ", strip=True) for node in body.select("p, h2, h3, li")),
        "content_html": content_html,
        "category": sections[-1].strip() or main_category or "",
        "main_category": main_category,
        "url": url,
        "image_url": image_url or (first_image["src"] if first_image else None),
        "published_at": parse_published_at(metadata.get("datePublished"))
                        or parse_published_at(date.get("datetime") if date else ""),
    }


def main(categories=None, days=30, limit_per_category=10):
    if days < 1 or limit_per_category < 1:
        raise ValueError("days và limit_per_category phải lớn hơn 0")
    selected = list(FEED_PATHS) if categories is None else list(categories)
    for topic in selected:
        if topic not in FEED_PATHS:
            raise ValueError(f"Chủ đề không hợp lệ: {topic}")
    now = datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    inserted = []
    seen = set()
    for topic in selected:
        print(f"Dân trí: {topic}", flush=True)
        try:
            entries = get_feed_articles(f"https://dantri.com.vn/rss/{FEED_PATHS[topic]}.rss")
        except Exception as exc:
            print(f"Không lấy được RSS {topic}: {type(exc).__name__}")
            continue
        finally:
            time.sleep(1)
        saved = 0
        for entry in entries:
            url = entry["url"]
            if url in seen:
                continue
            seen.add(url)
            if entry["published_at"] and not start <= entry["published_at"] <= now:
                continue
            with engine.connect() as connection:
                if article_exists(connection, url):
                    continue
            try:
                article = get_article(url, default_category=topic)
                article["published_at"] = article["published_at"] or entry["published_at"]
                if not article["title"] or not article["content"] or not article["published_at"]:
                    continue
                if not start <= article["published_at"] <= now:
                    continue
                with engine.begin() as connection:
                    if article_exists(connection, url):
                        continue
                    insert_article(connection, article)
                inserted.append(article)
                saved += 1
                print(f"Đã lưu: {article['title']}", flush=True)
            except Exception as exc:
                print(f"Không đọc được {url}: {type(exc).__name__}")
            finally:
                time.sleep(1)
            if saved >= limit_per_category:
                break
    print(f"Dân trí: đã lưu {len(inserted)} bài mới.")
    return inserted


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Thu thập tin từ RSS Dân trí.")
    parser.add_argument("--categories", nargs="+", choices=list(FEED_PATHS))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit-per-category", type=int, default=10)
    args = parser.parse_args()
    if args.days < 1 or args.limit_per_category < 1:
        parser.error("--days và --limit-per-category phải lớn hơn 0")
    main(args.categories, args.days, args.limit_per_category)
