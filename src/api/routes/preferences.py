from fastapi import APIRouter, Depends, HTTPException
from src.api.schemas import PreferencesRequest
from src.api.routes.auth import get_me

from src.recommendation.user_profile import (
    get_user_preferences,
    save_user_preferences,
)

router = APIRouter(prefix="/preferences", tags=["Preferences"])


@router.get("")
def get_preferences(user=Depends(get_me)):
    user_id = user["user_id"]

    return {
        "user_id": user_id,
        "preferences": get_user_preferences(user_id),
    }


@router.put("")
def update_preferences(
    request: PreferencesRequest,
    user=Depends(get_me),
):
    topics = []

    for topic in request.topics:
        topic = topic.strip()

        if not topic or len(topic) > 200:
            raise HTTPException(
                status_code=422,
                detail="Topic must contain 1 to 200 characters",
            )

        if topic not in topics:
            topics.append(topic)

    save_user_preferences(user["user_id"], topics)

    return {
        "message": "Preferences saved successfully",
        "topics": topics,
    }
