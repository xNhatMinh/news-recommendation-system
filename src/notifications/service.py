from sqlalchemy import text

from src.db.db import engine
from src.embedding.hybrid_search import MIN_RELEVANCE_SCORE, search_hybrid
from src.news_topics import get_main_topic
from src.notifications.sender import send_notification_to_user
from src.notifications.store import save_notification


def get_notification_preferences():
    # Lưu cả thông báo cho người dùng chưa đăng ký thiết bị FCM.
    with engine.connect() as connection:
        return connection.execute(text("""
            SELECT user_id, topic, weight FROM user_preferences
            ORDER BY user_id, id
        """)).fetchall()


def find_matching_articles(topic, new_articles, min_score=MIN_RELEVANCE_SCORE):
    if not new_articles:
        return []
    main_topic = get_main_topic(topic)
    if main_topic is not None:
        return [
            article
            for article in new_articles
            if (article.get("main_category") or article.get("category")) == main_topic
        ]

    article_urls = {article["url"] for article in new_articles}
    dates = [article["published_at"].date() for article in new_articles]
    results = search_hybrid(
        topic,
        min(dates),
        max(dates),
        top_k=len(new_articles),
        article_urls=article_urls,
    )
    return [article for article in results if article["hybrid_score"] >= min_score]


def notify_new_articles(new_articles):
    if not new_articles:
        return

    user_articles = {}
    for preference in get_notification_preferences():
        matches = find_matching_articles(preference.topic, new_articles)
        selected = user_articles.setdefault(preference.user_id, {})
        for article in matches:
            url = article["url"]
            if url not in selected or get_main_topic(preference.topic) is not None:
                selected[url] = preference.topic

    for user_id, matches in user_articles.items():
        try:
            created = sum(
                save_notification(user_id, url, topic) for url, topic in matches.items()
            )
            if not created:
                continue
            # Lưu database trước; lỗi gửi push không làm mất hộp thông báo.
            sent = send_notification_to_user(
                user_id=user_id,
                title="Tin mới",
                body=f"Có {created} bài báo mới phù hợp với sở thích của bạn.",
                data={"screen": "notifications"},
            )
            print(
                f"User {user_id}: đã lưu {created} thông báo, gửi push đến {sent} thiết bị."
            )
        except Exception as exc:
            print(f"Lỗi thông báo cho user {user_id}: {exc}")
