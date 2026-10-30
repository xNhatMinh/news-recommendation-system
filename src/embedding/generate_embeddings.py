import json

from sqlalchemy import text

from src.db.db import engine
from src.embedding.model import MODEL_NAME, model


def get_articles_without_embeddings():
    sql = text("""
        SELECT a.id, a.title, a.description, a.content
        FROM articles a
        LEFT JOIN article_embeddings e ON a.id = e.article_id
        WHERE e.article_id IS NULL
        ORDER BY a.id
    """)
    with engine.connect() as connection:
        return connection.execute(sql).fetchall()


def generate_embedding_text(article):
    """Ghép tiêu đề, mô tả và nội dung thành văn bản đầu vào."""
    return " ".join([article.title, article.description or "", article.content or ""])


def save_embeddings(articles, embeddings):
    sql = text("""
        INSERT INTO article_embeddings (article_id, embedding, model_name)
        VALUES (:article_id, :embedding, :model_name)
    """)
    with engine.begin() as connection:
        for article, vector in zip(articles, embeddings):
            connection.execute(
                sql,
                {
                    "article_id": article.id,
                    "embedding": json.dumps(vector.tolist()),
                    "model_name": MODEL_NAME,
                },
            )


def main():
    articles = get_articles_without_embeddings()
    print(f"Số bài chưa có embedding: {len(articles)}")
    if not articles:
        return

    texts = [generate_embedding_text(article) for article in articles]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)
    save_embeddings(articles, embeddings)
    print(f"Đã tạo và lưu {len(embeddings)} embedding.")


if __name__ == "__main__":
    main()
