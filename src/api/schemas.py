from datetime import date
from pydantic import BaseModel, EmailStr, Field


class RecommendationRequest(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    top_k: int = 10


class RecommendationItem(BaseModel):
    title: str
    description: str
    category: str | None
    url: str
    published_at: str | None
    embedding_score: float
    keyword_score: int
    hybrid_score: float
    personalized_score: float


class RecommendationResponse(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    results: list[RecommendationItem]


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8)


class RegisterResponse(BaseModel):
    user_id: int
    email: EmailStr
    message: str

class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=8)

class LoginResponse(BaseModel):
    user_id: int
    email: EmailStr
    message: str