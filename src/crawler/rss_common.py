"""Shared RSS collection flow; each source supplies its own URL and article parser."""
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from src.db.article_store import article_exists, insert_article

VIETNAM_TZ = timezone(timedelta(hours=7))


def read_rss(feed_url, canonicalize_url, parse_date, headers):
    response = requests.get(feed_url, headers=headers, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "xml")
    if soup.find("rss") is None:
        raise ValueError("Nguồn không trả về RSS hợp lệ")

    entries = []
    seen_urls = set()
    for item in soup.find_all("item"):
        link = item.find("link")
        if link is None:
            continue
        url = canonicalize_url(link.get_text(strip=True))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        date = item.find("pubDate")
        entries.append({
            "url": url,
            "published_at": parse_date(date.get_text() if date else ""),
        })
    return entries


def run_rss_crawler(
    *, source_name, feed_paths, feed_url, canonicalize_url, parse_date,
    get_article, categories=None, days=2, limit_per_category=10,
    max_articles=None, dry_run=False, require_topic_match=False,
    require_main_category=True, headers=None, feed_delay=1, article_delay=1,
):
    if days < 1 or limit_per_category < 1 or (max_articles is not None and max_articles < 1):
        raise ValueError("days và giới hạn số bài phải lớn hơn 0")

    selected = list(feed_paths) if categories is None else list(categories)
    for topic in selected:
        if topic not in feed_paths:
            raise ValueError(f"Chủ đề không hợp lệ: {topic}")

    if not dry_run:
        from src.db.db import engine

    now = datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    inserted = []
    seen_urls = set()

    for topic in selected:
        print(f"{source_name}: {topic}", flush=True)
        try:
            entries = read_rss(
                feed_url(topic, feed_paths[topic]), canonicalize_url, parse_date, headers
            )
        except Exception as exc:
            print(f"Không lấy được RSS {topic}: {type(exc).__name__}", flush=True)
            continue
        finally:
            time.sleep(feed_delay)

        saved = 0
        for entry in entries:
            url = entry["url"]
            if url in seen_urls:
                continue
            if entry["published_at"] and not start <= entry["published_at"] <= now:
                continue

            try:
                if not dry_run:
                    with engine.connect() as connection:
                        if article_exists(connection, url):
                            seen_urls.add(url)
                            continue

                article = get_article(url, topic)
                article["published_at"] = article["published_at"] or entry["published_at"]
                article_topic = article.get("main_category") or article.get("category")
                if require_topic_match and article_topic != topic:
                    continue
                if not all(article.get(key) for key in ("title", "content", "published_at")):
                    continue
                if require_main_category and not article.get("main_category"):
                    continue
                if not start <= article["published_at"] <= now:
                    continue

                seen_urls.add(url)
                if not dry_run:
                    with engine.begin() as connection:
                        if article_exists(connection, url):
                            continue
                        insert_article(connection, article)
                inserted.append(article)
                saved += 1
                label = "Đọc thử" if dry_run else "Đã lưu"
                print(f"{label}: {article['title']}", flush=True)
            except Exception as exc:
                print(f"Không đọc được {url}: {type(exc).__name__}", flush=True)
            finally:
                time.sleep(article_delay)

            if max_articles is not None and len(inserted) >= max_articles:
                return inserted
            if saved >= limit_per_category:
                break

    action = "đọc thử" if dry_run else "đã lưu"
    print(f"{source_name}: {action} {len(inserted)} bài mới.", flush=True)
    return inserted
