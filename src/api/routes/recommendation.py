from fastapi import APIRouter

from src.api.schemas import (
    RecommendationRequest,
    RecommendationResponse
)
from src.recommendation.recommender import recommend


router = APIRouter(
    prefix="/recommend",
    tags=["Recommendation"]
)


@router.post("", response_model=RecommendationResponse)
def get_recommendations(
    request: RecommendationRequest
):
    results = recommend(
        user_id=request.user_id,
        start_date=request.start_date,
        end_date=request.end_date,
        top_k=request.top_k
    )

    results = [
        {
            **article,
            "published_at": (
                article["published_at"].isoformat()
                if article["published_at"]
                else None
            )
        }
        for article in results
    ]

    return {
        "user_id": request.user_id,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "results": results
    }