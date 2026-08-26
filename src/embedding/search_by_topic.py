import json
import re
from pathlib import Path
from datetime import datetime

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


with open(
    DATA_DIR / "articles.json",
    "r",
    encoding="utf-8"
) as f:
    articles = json.load(f)


with open(
    DATA_DIR / "embeddings.json",
    "r",
    encoding="utf-8"
) as f:
    embeddings = json.load(f)


model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def get_date(date_text):

    match = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        date_text
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    return datetime(
        year,
        month,
        day
    ).date()


def search_by_topic(
    topic,
    start_date,
    end_date,
    top_k=10
):

    topic_vector = model.encode(
        [topic]
    )

    article_map = {}

    for article in articles:
        article_map[article["url"]] = article

    results = []

    for embedding in embeddings:

        url = embedding["url"]

        if url not in article_map:
            continue

        article = article_map[url]

        published_date = get_date(
            article["published_at"]
        )

        if published_date is None:
            continue

        if published_date < start_date:
            continue

        if published_date > end_date:
            continue

        embedding_score = cosine_similarity(
            topic_vector,
            [embedding["vector"]]
        )[0][0]

        title = article["title"].lower()
        description = article["description"].lower()

        keyword_score = 0

        if topic.lower() in title:
            keyword_score = 1

        elif topic.lower() in description:
            keyword_score = 1

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
            "published_at": article["published_at"],
            "embedding_score": float(embedding_score),
            "keyword_score": keyword_score,
            "score": float(hybrid_score)
        })

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:top_k]


def main():

    print("=" * 60)
    print("SEARCH NEWS BY TOPIC")
    print("=" * 60)

    topic = input("Chủ đề: ")

    start_date_text = input(
        "Từ ngày (dd/mm/yyyy): "
    )

    end_date_text = input(
        "Đến ngày (dd/mm/yyyy): "
    )

    start_date = datetime.strptime(
        start_date_text,
        "%d/%m/%Y"
    ).date()

    end_date = datetime.strptime(
        end_date_text,
        "%d/%m/%Y"
    ).date()

    if start_date > end_date:
        print(
            "Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc."
        )
        return

    results = search_by_topic(
        topic,
        start_date,
        end_date,
        top_k=10
    )

    print("\n" + "=" * 60)
    print(f"Chủ đề: {topic}")
    print(
        f"Thời gian: {start_date_text} - {end_date_text}"
    )
    print("=" * 60)

    if not results:
        print("Không tìm thấy bài báo phù hợp.")
        return

    print(
        f"\nTìm thấy {len(results)} bài báo liên quan.\n"
    )

    for i, result in enumerate(results, start=1):

        print("-" * 60)

        print(f"{i}. {result['title']}")

        print(
            f"Ngày đăng: {result['published_at']}"
        )

        print(
            f"Hybrid score: {result['score']:.4f}"
        )

        print(
            f"Embedding score: "
            f"{result['embedding_score']:.4f}"
        )

        print(
            f"Keyword: {result['keyword_score']}"
        )

        print(
            f"URL: {result['url']}"
        )


if __name__ == "__main__":
    main()