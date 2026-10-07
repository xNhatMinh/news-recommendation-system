import json

from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from src.db.db import engine


MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)

model = SentenceTransformer(MODEL_NAME)


def get_articles_without_embeddings():
    sql = text("""
        SELECT
            a.id,
            a.title,
            a.description,
            a.content
        FROM articles a
        LEFT JOIN article_embeddings e
            ON a.id = e.article_id
        WHERE e.article_id IS NULL
        ORDER BY a.id
    """)

    with engine.connect() as connection:
        rows = connection.execute(sql).fetchall()

    return rows


def generate_embedding_text(article):
    return (
        article.title
        + " "
        + (article.description or "")
        + " "
        + (article.content or "")
    )


def save_embeddings(articles, embeddings):
    sql = text("""
        INSERT INTO article_embeddings (
            article_id,
            embedding,
            model_name
        )
        VALUES (
            :article_id,
            :embedding,
            :model_name
        )
    """)

    with engine.begin() as connection:
        for article, embedding in zip(
            articles,
            embeddings
        ):
            connection.execute(
                sql,
                {
                    "article_id": article.id,
                    "embedding": json.dumps(
                        embedding.tolist()
                    ),
                    "model_name": MODEL_NAME
                }
            )


def main():
    print("=" * 60)
    print("GENERATE EMBEDDINGS")
    print("=" * 60)

    articles = get_articles_without_embeddings()

    print(
        f"Articles chưa có embedding: "
        f"{len(articles)}"
    )

    if not articles:
        print("Không có bài nào cần xử lý.")
        return

    texts = [
        generate_embedding_text(article)
        for article in articles
    ]

    print("Đang tạo embeddings...")

    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True
    )

    print("Đang lưu embeddings vào MySQL...")

    save_embeddings(
        articles,
        embeddings
    )

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

    print(
        f"Đã tạo embedding: "
        f"{len(embeddings)}"
    )


if __name__ == "__main__":
    main()