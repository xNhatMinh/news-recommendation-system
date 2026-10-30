from datetime import datetime

from src.embedding.hybrid_search import MIN_RELEVANCE_SCORE, search_hybrid
from src.news_topics import get_main_topic
from src.recommendation.history import save_recommendation_history
from src.recommendation.user_profile import get_user_preferences


def recommend(user_id, start_date, end_date, top_k=10):
    """Tìm tin cho từng sở thích, bỏ trùng URL rồi xếp theo điểm cá nhân."""
    preferences = get_user_preferences(user_id)
    all_results = {}

    for preference in preferences:
        topic = preference["topic"]
        weight = preference["weight"]
        is_main_topic = get_main_topic(topic) is not None
        results = search_hybrid(topic, start_date, end_date, top_k=top_k)

        for article in results:
            if not is_main_topic and article["hybrid_score"] < MIN_RELEVANCE_SCORE:
                continue

            url = article["url"]
            score = article["hybrid_score"] * weight
            previous = all_results.get(url)
            if previous is None:
                all_results[url] = {**article, "personalized_score": score}
            elif score > previous["personalized_score"]:
                previous["personalized_score"] = score

    results = sorted(
        all_results.values(), key=lambda item: item["personalized_score"], reverse=True
    )
    return results[:top_k]


def main():
    # Phần chạy terminal có thêm bước tổng hợp; API chỉ dùng hàm recommend.
    from src.summarization.summarizer import save_summary, summarize_articles

    user_id = int(input("User ID: "))
    start_date = datetime.strptime(input("Từ ngày (dd/mm/yyyy): "), "%d/%m/%Y").date()
    end_date = datetime.strptime(input("Đến ngày (dd/mm/yyyy): "), "%d/%m/%Y").date()
    if start_date > end_date:
        print("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.")
        return

    results = recommend(user_id, start_date, end_date)
    if not results:
        print("Không tìm thấy bài báo phù hợp.")
        return
    save_recommendation_history(user_id, results)

    for rank, article in enumerate(results, start=1):
        print(f"{rank}. {article['title']}")
        print(f"Ngày đăng: {article['published_at']}")
        print(f"Điểm hybrid: {article['hybrid_score']:.4f}")
        print(f"Điểm cá nhân: {article['personalized_score']:.4f}")
        print(f"URL: {article['url']}\n")

    topic = f"Tin tức phù hợp với người dùng {user_id}"
    summary = summarize_articles(topic, start_date, end_date, results)
    save_summary(user_id, topic, start_date, end_date, results, summary)
    print(summary)


if __name__ == "__main__":
    main()
