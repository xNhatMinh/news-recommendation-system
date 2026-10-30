import json
from pathlib import Path

from sqlalchemy import text

from src.db.db import engine

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "embeddings.json"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def import_embeddings():

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        embeddings = json.load(f)

    success = 0
    skipped = 0

    with engine.begin() as connection:

        for item in embeddings:

            url = item.get("url")
            vector = item.get("vector")

            if not url or not vector:
                skipped += 1
                continue

            # Tìm article_id dựa vào URL
            result = connection.execute(
                text("""
                    SELECT id
                    FROM articles
                    WHERE url = :url
                """),
                {"url": url},
            ).fetchone()

            if result is None:
                print(f"Không tìm thấy article: {url}")
                skipped += 1
                continue

            article_id = result[0]

            # Insert embedding
            connection.execute(
                text("""
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
                    ON DUPLICATE KEY UPDATE
                        embedding = VALUES(embedding),
                        model_name = VALUES(model_name)
                """),
                {
                    "article_id": article_id,
                    "embedding": json.dumps(vector),
                    "model_name": MODEL_NAME,
                },
            )

            success += 1

    print(f"Đã import: {success} embeddings")
    print(f"Bỏ qua: {skipped}")


if __name__ == "__main__":
    import_embeddings()
