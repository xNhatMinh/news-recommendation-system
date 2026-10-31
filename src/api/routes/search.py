from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.routes.auth import get_me
from src.api.schemas import SearchArticlesResponse
from src.embedding.hybrid_search import MIN_RELEVANCE_SCORE, search_hybrid
from src.news_topics import get_main_topic

router = APIRouter(prefix="/articles", tags=["Articles"])


@router.get("/search", response_model=SearchArticlesResponse)
def search_articles(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(get_me),
):
    query = " ".join(q.split())
    if not query:
        raise HTTPException(status_code=422, detail="Hãy nhập từ khóa tìm kiếm")

    # Tìm trong toàn bộ tin đã lưu, không giới hạn theo chủ đề yêu thích.
    articles = search_hybrid(query, date(1000, 1, 1), date.max, top_k=None)
    main_topic = get_main_topic(query)
    matches = [
        article
        for article in articles
        if main_topic is not None
        or article["keyword_score"]
        or article["hybrid_score"] >= MIN_RELEVANCE_SCORE
    ]
    matches.sort(
        key=lambda article: (
            article["hybrid_score"],
            str(article["published_at"] or ""),
            article["url"],
        ),
        reverse=True,
    )
    return {
        "results": matches[offset : offset + limit],
        "has_more": len(matches) > offset + limit,
    }
