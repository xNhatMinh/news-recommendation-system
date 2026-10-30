from fastapi import APIRouter, Depends
from src.api.routes.auth import get_me
from src.recommendation.history import save_recommendation_history

from src.api.schemas import RecommendationRequest, RecommendationResponse
from src.recommendation.recommender import recommend

router = APIRouter(prefix="/recommend", tags=["Recommendation"])


@router.post("", response_model=RecommendationResponse)
def recommend_articles(request: RecommendationRequest, user=Depends(get_me)):
    results = recommend(
        user_id=user["user_id"],
        start_date=request.start_date,
        end_date=request.end_date,
        top_k=request.top_k,
    )

    if results:
        save_recommendation_history(user_id=user["user_id"], articles=results)

    results = [
        {
            **article,
            "published_at": (
                article["published_at"].isoformat() if article["published_at"] else None
            ),
        }
        for article in results
    ]

    return {
        "user_id": user["user_id"],
        "start_date": request.start_date,
        "end_date": request.end_date,
        "results": results,
    }
