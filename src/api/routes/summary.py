from fastapi import APIRouter, Depends, HTTPException

from src.api.routes.auth import get_me
from src.api.schemas import SummaryRequest
from src.news_topics import get_main_topic
from src.embedding.hybrid_search import MIN_RELEVANCE_SCORE, search_hybrid
from src.summarization.summarizer import summarize_articles

router = APIRouter(prefix="/summary", tags=["Summary"])


@router.post("")
def create_summary(request: SummaryRequest, user=Depends(get_me)):
    if request.start_date > request.end_date:
        raise HTTPException(
            status_code=400, detail="Ngày bắt đầu phải trước hoặc bằng ngày kết thúc"
        )

    articles = search_hybrid(
        topic=request.topic,
        start_date=request.start_date,
        end_date=request.end_date,
        top_k=5,
    )

    # Chủ đề chính đã lọc đúng nhóm; từ khóa riêng vẫn cần ngưỡng liên quan.
    is_main_topic = get_main_topic(request.topic) is not None
    if not is_main_topic:
        articles = [
            article
            for article in articles
            if article["hybrid_score"] >= MIN_RELEVANCE_SCORE
        ]

    if not articles:
        raise HTTPException(
            status_code=404, detail="Chưa có bài báo phù hợp để tổng hợp"
        )

    summary = summarize_articles(
        topic=request.topic,
        start_date=request.start_date,
        end_date=request.end_date,
        articles=articles,
    )

    if not summary or not summary.strip():
        raise HTTPException(
            status_code=502, detail="Gemini chưa trả về nội dung tổng hợp"
        )

    return {
        "summary": summary,
        "sources": [
            {"title": article["title"], "url": article["url"]} for article in articles
        ],
    }
