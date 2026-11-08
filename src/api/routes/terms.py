"""Explain a selected term using the stored article as context."""
import logging
import re
import unicodedata
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from src.db.db import engine
from src.summarization.term_explainer import explain_term

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/articles", tags=["Articles"])

class TermRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    term: str = Field(min_length=1, max_length=120)

    @field_validator("term")
    @classmethod
    def clean_term(cls, value):
        value = " ".join(value.split())
        if not value or len(value.split()) > 15:
            raise ValueError("Chọn một từ hoặc cụm từ ngắn")
        return value

def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())

@router.post("/explain-term")
def explain_article_term(request: TermRequest):
    with engine.connect() as connection:
        article = connection.execute(text(
            "SELECT title, description, content, url FROM articles WHERE url = :url LIMIT 1"
        ), {"url": request.url}).mappings().first()
    if article is None:
        raise HTTPException(404, "Không tìm thấy bài báo")
    body = normalized(" ".join(str(article.get(k) or "") for k in ("title", "description", "content")))
    term = normalized(request.term)
    match = re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", body)
    if match is None:
        raise HTTPException(400, "Thuật ngữ không có trong nội dung bài báo đã lưu")
    context = body[max(0, match.start()-900):match.end()+900]
    try:
        result = explain_term(request.term, article["title"], context)
    except RuntimeError:
        raise HTTPException(503, "Chưa cấu hình dịch vụ giải thích AI") from None
    except Exception:
        logger.warning("Term explanation provider failed")
        raise HTTPException(502, "Chưa thể giải thích lúc này. Hãy thử lại.") from None
    if not result or not result.strip():
        raise HTTPException(502, "AI chưa trả về lời giải thích. Hãy thử lại.")
    return {"term": request.term, "explanation": result.strip(), "source_url": article["url"]}
