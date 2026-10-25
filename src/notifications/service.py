from sqlalchemy import text

from src.db.db import engine
from src.embedding.hybrid_search import search_hybrid
from src.notifications.sender import send_notification_to_user


def get_notification_preferences():
    sql = text("""
        SELECT DISTINCT
            p.user_id,
            p.topic,
            p.weight
        FROM user_preferences p
        INNER JOIN user_devices d
            ON p.user_id = d.user_id
    """)

    with engine.connect() as connection:
        preferences = connection.execute(sql).fetchall()

    return preferences

def find_matching_articles(topic, new_articles, min_score=0.5):
    if not new_articles:
        return []

    article_urls = {
        article["url"] for article in new_articles
    }

    dates = [
        article["published_at"].date()
        for article in new_articles
    ]

    results = search_hybrid(
        topic=topic,
        start_date=min(dates),
        end_date=max(dates),
        top_k=len(new_articles),
        article_urls=article_urls
    )

    return [
        article
        for article in results
        if article["hybrid_score"] >= min_score
    ]

def notify_new_articles(new_articles):
    if not new_articles:
        return

    preferences = get_notification_preferences()
    user_articles = {}

    for preference in preferences:
        matches = find_matching_articles(
            topic=preference.topic,
            new_articles=new_articles
        )

        if not matches:
            continue

        user_id = preference.user_id

        if user_id not in user_articles:
            user_articles[user_id] = set()

        for article in matches:
            user_articles[user_id].add(article["url"])

    for user_id, article_urls in user_articles.items():
        try:
            sent_count = send_notification_to_user(
                user_id=user_id,
                title="Tin mới",
                body=(
                    f"Có {len(article_urls)} bài báo mới "
                    "phù hợp với sở thích của bạn."
                )
            )

            print(
                f"Tài khoản {user_id}: "
                f"Firebase chấp nhận gửi đến {sent_count} thiết bị"
            )

        except Exception as e:
            print(f"Lỗi gửi thông báo cho tài khoản {user_id}: {e}")