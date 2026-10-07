from fastapi import APIRouter

from src.recommendation.history import get_recommendation_history


router = APIRouter(
    prefix="/history",
    tags=["History"]
)


@router.get("/{user_id}")
def get_history(user_id: int, limit: int = 20):
    return {
        "user_id": user_id,
        "history": get_recommendation_history(
            user_id=user_id,
            limit=limit
        )
    }