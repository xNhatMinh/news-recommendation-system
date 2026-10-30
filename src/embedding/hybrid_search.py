import json

from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import text

from src.db.db import engine
from src.embedding.model import model
from src.news_topics import get_main_topic

MIN_RELEVANCE_SCORE = 0.5


def keyword_match(topic, article):
    content = " ".join([article["title"], article["description"], article["content"]])
    return 1 if topic.lower() in content.lower() else 0


def search_hybrid(topic, start_date, end_date, top_k=10, article_urls=None):
    """Lọc tin, so sánh embedding, cộng điểm từ khóa rồi lấy top kết quả."""
    topic = topic.strip()
    main_topic = get_main_topic(topic)
    topic_vector = model.encode([topic])

    sql = """
        SELECT a.id, a.title, a.description, a.content,
               COALESCE(NULLIF(a.main_category, ''), a.category) AS category,
               a.url, a.image_url, a.published_at, e.embedding
        FROM articles a
        INNER JOIN article_embeddings e ON a.id = e.article_id
        WHERE DATE(a.published_at) BETWEEN :start_date AND :end_date
    """
    parameters = {"start_date": start_date, "end_date": end_date}
    if main_topic is not None:
        sql += " AND COALESCE(NULLIF(a.main_category, ''), a.category) = :main_topic"
        parameters["main_topic"] = main_topic

    with engine.connect() as connection:
        rows = connection.execute(text(sql), parameters).fetchall()

    results = []
    for row in rows:
        if article_urls is not None and row.url not in article_urls:
            continue
        article = {
            "title": row.title,
            "description": row.description or "",
            "content": row.content or "",
            "category": row.category,
            "url": row.url,
            "image_url": row.image_url,
            "published_at": row.published_at,
        }

        article_vector = json.loads(row.embedding)
        embedding_score = cosine_similarity(topic_vector, [article_vector])[0][0]
        keyword_score = keyword_match(topic, article)
        hybrid_score = embedding_score
        if keyword_score:
            hybrid_score += 0.3

        results.append(
            {
                **article,
                "embedding_score": float(embedding_score),
                "keyword_score": keyword_score,
                "hybrid_score": float(hybrid_score),
            }
        )

    results.sort(key=lambda article: article["hybrid_score"], reverse=True)
    return results[:top_k]
