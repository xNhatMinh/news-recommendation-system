from fastapi import APIRouter, Depends, Query

from src.api.routes.auth import get_me
from src.recommendation.history import get_recommendation_history

router = APIRouter(prefix="/history", tags=["History"])


@router.get("")
def get_history(user=Depends(get_me), limit: int = Query(default=20, ge=1, le=100)):
    user_id = user["user_id"]

    return {
        "user_id": user_id,
        "history": get_recommendation_history(user_id=user_id, limit=limit),
    }
