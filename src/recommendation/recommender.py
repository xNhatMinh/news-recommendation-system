
from src.embedding.hybrid_search import MIN_RELEVANCE_SCORE, search_hybrid
from src.news_topics import get_main_topic
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