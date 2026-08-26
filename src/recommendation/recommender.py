from datetime import datetime

from src.embedding.hybrid_search import search_hybrid
from src.summarization.summarizer import summarize_articles, save_summary

def recommend(
    topic,
    start_date,
    end_date,
    top_k=10
):
    results = search_hybrid(
        topic,
        start_date,
        end_date,
        top_k
    )

    return results


def main():

    print("=" * 60)
    print("NEWS RECOMMENDATION")
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

    results = recommend(
        topic,
        start_date,
        end_date,
        top_k=10
    )

    print("\n" + "=" * 60)
    print("KẾT QUẢ GỢI Ý")
    print("=" * 60)

    if not results:
        print("Không tìm thấy bài báo phù hợp.")
        return

    for i, article in enumerate(results, start=1):

        print("-" * 60)

        print(
            f"{i}. {article['title']}"
        )

        print(
            f"Ngày đăng: {article['published_at']}"
        )

        print(
            f"Hybrid score: {article['hybrid_score']:.4f}"
        )

        print(
            f"URL: {article['url']}"
        )

    print("\nĐang tổng hợp bằng Gemini...")

    summary = summarize_articles(
        topic,
        start_date,
        end_date,
        results
    )

    save_summary(
        topic,
        start_date,
        end_date,
        results,
        summary
    )

    print("\n" + "=" * 60)
    print("BẢN TỔNG HỢP")
    print("=" * 60)

    print(summary)


if __name__ == "__main__":
    main()