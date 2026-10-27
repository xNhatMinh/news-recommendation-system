import json

from datetime import datetime

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import text

from src.db.db import engine
from src.news_topics import MAIN_TOPICS


model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def keyword_match(topic, article):
    topic = topic.lower()

    text_content = (
        article["title"]
        + " "
        + article["description"]
        + " "
        + article["content"]
    ).lower()

    return 1 if topic in text_content else 0


def search_hybrid(
    topic,
    start_date,
    end_date,
    top_k=10,
    article_urls=None
):

    topic = topic.strip()
    main_topic = next((name for name in MAIN_TOPICS if name.casefold() == topic.casefold()), None)
    topic_vector = model.encode([topic])

    sql = """
        SELECT
            a.id,
            a.title,
            a.description,
            a.content,
            COALESCE(NULLIF(a.main_category, ''), a.category) AS category,
            a.url,
            a.image_url,
            a.published_at,
            e.embedding
        FROM articles a
        INNER JOIN article_embeddings e
            ON a.id = e.article_id
        WHERE DATE(a.published_at)
              BETWEEN :start_date AND :end_date
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
            "published_at": row.published_at
        }

        # MySQL JSON → Python list
        article_vector = json.loads(row.embedding)

        embedding_score = cosine_similarity(
            topic_vector,
            [article_vector]
        )[0][0]

        keyword_score = keyword_match(
            topic,
            article
        )

        if keyword_score == 1:
            hybrid_score = embedding_score + 0.3
        else:
            hybrid_score = embedding_score

        results.append({
            "title": article["title"],
            "description": article["description"],
            "content": article["content"],
            "category": article["category"],
            "url": article["url"],
            "image_url": article["image_url"],
            "published_at": article["published_at"],
            "embedding_score": float(embedding_score),
            "keyword_score": keyword_score,
            "hybrid_score": float(hybrid_score)
        })

    results.sort(
        key=lambda x: x["hybrid_score"],
        reverse=True
    )

    return results[:top_k]