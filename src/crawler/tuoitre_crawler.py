"""Lấy tin từ RSS Tuổi Trẻ và giữ nội dung, ảnh theo thứ tự bài gốc."""

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
from src.news_topics import get_main_topic

FEED_PATHS = {
    "Thời sự": "thoi-su", "Thế giới": "the-gioi",
    "Kinh doanh": "kinh-doanh", "Khoa học": "khoa-hoc",
    "Thể thao": "the-thao", "Giải trí": "giai-tri",
    "Sức khỏe": "suc-khoe", "Công nghệ": "nhip-song-so",
    "Giáo dục": "giao-duc", "Pháp luật": "phap-luat",
    "Du lịch": "du-lich", "Đời sống": "nhip-song-tre",
    "Xe": "xe", "Bất động sản": "nha-dat",
}
SECTION_TOPICS = {"Nhịp sống số": "Công nghệ", "Văn hóa": "Giải trí", "Nhà đất": "Bất động sản", "Nhịp sống trẻ": "Đời sống"}
VIETNAM_TZ = timezone(timedelta(hours=7))
HEADERS = {"User-Agent": "Newsora/1.0 (academic news reader)"}
BODY_SELECTOR = ".detail-content"


def parse_published_at(value):
    if not value:
        return None
    value = " ".join(str(value).split())
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            result = None
        if result is None:
            for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%d/%m/%Y %H:%M"):
                try:
                    result = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    pass
    if result is not None and result.tzinfo is not None:
        result = result.astimezone(VIETNAM_TZ).replace(tzinfo=None)
    return result


def canonical_article_url(value):
    try:
        parsed = urlparse(value.strip())
        if (parsed.scheme not in ("http", "https") or parsed.hostname not in ("tuoitre.vn", "www.tuoitre.vn")
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
            return None
        if not re.fullmatch(r"/[^/]+-\d{10,22}\.htm", parsed.path):
            return None
        return "https://tuoitre.vn" + parsed.path
    except ValueError:
        return None


def get_feed_articles(feed_url):
    response = requests.get(feed_url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "xml")
    if soup.find("rss") is None:
        raise ValueError("Nguồn không trả về RSS hợp lệ")
    articles = []
    seen = set()
    for item in soup.find_all("item"):
        link = item.find("link")
        if link is None:
            continue
        url = canonical_article_url(link.get_text(strip=True))
        if not url:
            continue
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
        '.ads, .adsbygoogle, .related-news, .related-box, .content-box-related, '
        '[type="RelatedNewsBox"], [type="RelatedOneNews"], [type="VideoStream"], '
        '[type="Video"], [type="Advertisement"], .readmore-body-box'
    ):
        node.decompose()

    for element in body.select("img, picture source"):
        src = absolute_url(
            element.get("data-original") or element.get("data-src") or element.get("src"), url
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


def _json_objects(value):
    if isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _json_objects(value["@graph"])
    elif isinstance(value, list):
        for item in value:
            yield from _json_objects(item)


def parse_article(html, url, default_category=None):
    soup = BeautifulSoup(html, "lxml")
    metadata = {}
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = _json_objects(json.loads(script.get_text()))
            metadata = next((obj for obj in objects if any(kind in ("NewsArticle", "Article")
                for kind in ([obj.get("@type")] if isinstance(obj.get("@type"), str) else obj.get("@type") or []))), {})
        except (ValueError, TypeError):
            continue
        if metadata:
            break
    def meta(selector):
        node = soup.select_one(selector)
        return node.get("content", "") if node else ""
    title = soup.select_one("h1.detail-title, h1")
    sapo = soup.select_one(".detail-sapo")
    category = meta('meta[property="article:section"]') or str(metadata.get("articleSection") or "")
    main = get_main_topic(category) or SECTION_TOPICS.get(category)
    if main is None:
        for link in soup.select('.detail-cate a, .breadcrumb a'):
            label = link.get_text(" ", strip=True)
            main = get_main_topic(label) or SECTION_TOPICS.get(label)
            if main:
                break
    main = main or default_category
    content_html = get_content_html(soup, url)
    body = BeautifulSoup(content_html, "html.parser")
    date = soup.select_one("time[datetime]")
    published = (parse_published_at(meta('meta[property="article:published_time"]'))
                 or parse_published_at(metadata.get("datePublished"))
                 or parse_published_at(date.get("datetime") if date else None))
    first_image = body.select_one("img[src]")
    return {
        "title": title.get_text(" ", strip=True) if title else str(metadata.get("headline") or ""),
        "description": sapo.get_text(" ", strip=True) if sapo else meta('meta[name="description"]') or str(metadata.get("description") or ""),
        "content": "\n".join(n.get_text(" ", strip=True) for n in body.select("p, h2, h3, h4, li")),
        "content_html": content_html, "category": category or main or "", "main_category": main,
        "image_url": absolute_url(meta('meta[property="og:image"]'), url) or (first_image["src"] if first_image else None),
        "published_at": published, "url": url,
    }


def get_article(url, default_category=None):
    canonical = canonical_article_url(url)
    if canonical is None:
        raise ValueError("Đường dẫn bài Tuổi Trẻ không hợp lệ")
    response = requests.get(canonical, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return parse_article(response.content, canonical, default_category)


def main(categories=None, days=2, limit_per_category=10, max_articles=None, dry_run=False):
    if days < 1 or limit_per_category < 1 or (max_articles is not None and max_articles < 1):
        raise ValueError("days và limit_per_category phải lớn hơn 0")
    selected = list(FEED_PATHS) if categories is None else list(categories)
    for topic in selected:
        if topic not in FEED_PATHS:
            raise ValueError(f"Chủ đề không hợp lệ: {topic}")
    if not dry_run:
        from src.db.db import engine
    now = datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    inserted = []
    seen = set()
    for topic in selected:
        print(f"Tuổi Trẻ: {topic}", flush=True)
        try:
            entries = get_feed_articles(f"https://tuoitre.vn/{FEED_PATHS[topic]}.rss")
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
            try:
                if not dry_run:
                    with engine.connect() as connection:
                        if article_exists(connection, url):
                            continue
                article = get_article(url, default_category=topic)
                article["published_at"] = article["published_at"] or entry["published_at"]
                if not all(article.get(k) for k in ("title", "content", "published_at", "main_category")):
                    continue
                if not start <= article["published_at"] <= now:
                    continue
                if not dry_run:
                    with engine.begin() as connection:
                        if article_exists(connection, url):
                            continue
                        insert_article(connection, article)
                inserted.append(article)
                saved += 1
                print(f"{'Đọc thử' if dry_run else 'Đã lưu'}: {article['title']}", flush=True)
            except Exception as exc:
                print(f"Không đọc được {url}: {type(exc).__name__}")
            finally:
                time.sleep(1)
            if max_articles is not None and len(inserted) >= max_articles:
                return inserted
            if saved >= limit_per_category:
                break
    print(f"Tuổi Trẻ: {'đọc thử' if dry_run else 'đã lưu'} {len(inserted)} bài.")
    return inserted


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Thu thập tin từ RSS Tuổi Trẻ.")
    parser.add_argument("--categories", nargs="+", choices=list(FEED_PATHS))
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--limit-per-category", type=int, default=10)
    parser.add_argument("--max-articles", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ trích xuất, không ghi cơ sở dữ liệu")
    args = parser.parse_args()
    if args.days < 1 or args.limit_per_category < 1 or (args.max_articles is not None and args.max_articles < 1):
        parser.error("--days và --limit-per-category phải lớn hơn 0")
    main(args.categories, args.days, args.limit_per_category, args.max_articles, args.dry_run)
