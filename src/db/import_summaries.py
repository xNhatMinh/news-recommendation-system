import json
from pathlib import Path
from datetime import datetime

from sqlalchemy import text

from src.db.db import engine


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

INPUT_FILE = DATA_DIR / "summaries.json"


def parse_date(date_text):
    return datetime.strptime(
        date_text,
        "%d/%m/%Y"
    ).date()


def import_summaries():

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        summaries = json.load(f)

    success = 0
    skipped = 0

    with engine.begin() as connection:

        for summary_data in summaries:
            result = connection.execute(
                text("""
                    INSERT INTO summaries (
                        topic,
                        start_date,
                        end_date,
                        summary
                    )
                    VALUES (
                        :topic,
                        :start_date,
                        :end_date,
                        :summary
                    )
                """),
                {
                    "topic": summary_data["topic"],
                    "start_date": parse_date(
                        summary_data["start_date"]
                    ),
                    "end_date": parse_date(
                        summary_data["end_date"]
                    ),
                    "summary": summary_data["summary"]
                }
            )

            summary_id = result.lastrowid


            for article in summary_data["articles"]:

                result = connection.execute(
                    text("""
                        SELECT id
                        FROM articles
                        WHERE url = :url
                    """),
                    {
                        "url": article["url"]
                    }
                ).fetchone()

                if result is None:
                    print(
                        f"Không tìm thấy article: "
                        f"{article['title']}"
                    )
                    skipped += 1
                    continue

                article_id = result[0]

                connection.execute(
                    text("""
                        INSERT INTO summary_articles (
                            summary_id,
                            article_id,
                            hybrid_score
                        )
                        VALUES (
                            :summary_id,
                            :article_id,
                            :hybrid_score
                        )
                    """),
                    {
                        "summary_id": summary_id,
                        "article_id": article_id,
                        "hybrid_score": article["hybrid_score"]
                    }
                )

            success += 1

    print(f"Đã import: {success} summaries")
    print(f"Bỏ qua: {skipped} articles")


if __name__ == "__main__":
    import_summaries()