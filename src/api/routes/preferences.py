from fastapi import APIRouter

from src.recommendation.user_profile import (
    get_user_preferences,
    update_user_preference
)


router = APIRouter(
    prefix="/preferences",
    tags=["Preferences"]
)


@router.get("/{user_id}")
def get_preferences(user_id: int):
    return {
        "user_id": user_id,
        "preferences": get_user_preferences(user_id)
    }


@router.put("/{user_id}")
def update_preference(
    user_id: int,
    topic: str,
    weight: float
):
    update_user_preference(
        user_id=user_id,
        topic=topic,
        weight=weight
    )

    return {
        "message": "Preference updated successfully",
        "user_id": user_id,
        "topic": topic,
        "weight": weight
    }