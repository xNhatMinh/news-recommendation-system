from datetime import datetime

from src.embedding.hybrid_search import search_hybrid
from src.summarization.summarizer import summarize_articles, save_summary
from src.recommendation.user_profile import get_user_preferences
from src.recommendation.history import save_recommendation_history


def recommend(
    user_id,
    start_date,
    end_date,
    top_k=10
):
    preferences = get_user_preferences(user_id)

    all_results = {}

    for preference in preferences:

        topic = preference["topic"]
        weight = preference["weight"]

        results = search_hybrid(
            topic,
            start_date,
            end_date,
            top_k=top_k
        )

        for article in results:

            url = article["url"]

            personalized_score = (
                article["hybrid_score"] * weight
            )

            if url not in all_results:
                all_results[url] = {
                    **article,
                    "personalized_score": personalized_score
                }

            else:
                if personalized_score > all_results[url]["personalized_score"]:
                    all_results[url]["personalized_score"] = personalized_score

    results = list(all_results.values())

    results.sort(
        key=lambda x: x["personalized_score"],
        reverse=True
    )

    return results[:top_k]


def main():

    print("=" * 60)
    print("NEWS RECOMMENDATION")
    print("=" * 60)

    user_id = int(input("User ID: "))

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
        user_id,
        start_date,
        end_date,
        top_k=10
    )

    save_recommendation_history(
        user_id,
        results
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
            f"Hybrid score: "
            f"{article['hybrid_score']:.4f}"
        )

        print(
            f"Personalized score: "
            f"{article['personalized_score']:.4f}"
        )

        print(
            f"URL: {article['url']}"
        )

    print("\n" + "=" * 60)
    print("ĐANG TỔNG HỢP BẰNG GEMINI...")
    print("=" * 60)

    summary_topic = (
        f"Tin tức phù hợp với người dùng {user_id}"
    )

    summary = summarize_articles(
        summary_topic,
        start_date,
        end_date,
        results
    )

    save_summary(
        summary_topic,
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