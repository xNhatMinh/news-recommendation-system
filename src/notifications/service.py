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
            SELECT user_id, topic FROM user_preferences
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
        created = sent = 0
        for url, topic in matches.items():
            try:
                # Lưu từng bài trước; lỗi push không làm mất hộp thông báo.
                if not save_notification(user_id, url, topic):
                    continue
                created += 1
                with engine.connect() as connection:
                    article = connection.execute(
                        text("SELECT id, title, description FROM articles WHERE url = :url"),
                        {"url": url},
                    ).mappings().one()
                sent += send_notification_to_user(
                    user_id=user_id,
                    title=article["title"],
                    body=(article["description"] or "").strip() or f"Tin mới về {topic}.",
                    data={
                        "screen": "notifications",
                        "article_url": url,
                        "topic": topic,
                        "notification_tag": f"newsora_article_{article['id']}",
                    },
                )
            except Exception as exc:
                print(f"Lỗi thông báo cho user {user_id}, bài {url}: {exc}")
        if created:
            print(f"User {user_id}: đã lưu {created} thông báo, gửi {sent} thông báo đẩy theo từng bài.")
