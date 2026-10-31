from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class RecommendationRequest(BaseModel):
    start_date: date
    end_date: date
    top_k: int = 10


class RecommendationItem(BaseModel):
    title: str
    description: str
    category: str | None
    url: str
    image_url: str | None = None
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


class ArticleListItem(BaseModel):
    title: str
    description: str
    category: str | None
    url: str
    image_url: str | None = None
    published_at: datetime | None


class SearchArticlesResponse(BaseModel):
    results: list[ArticleListItem]
    has_more: bool


class LatestArticlesResponse(BaseModel):
    results: list[ArticleListItem]
    categories: list[str]
    has_more: bool


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
    access_token: str
    token_type: str


class PreferencesRequest(BaseModel):
    topics: list[str]


class DeviceTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=1, max_length=512)


class SummaryRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date


class NotificationItem(BaseModel):
    id: int
    topic: str
    title: str
    description: str
    url: str
    image_url: str | None = None
    is_read: bool
    created_at: datetime


class NotificationCounts(BaseModel):
    total_count: int
    unread_count: int


class NotificationsResponse(NotificationCounts):
    results: list[NotificationItem]
    has_more: bool


class BookmarkRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class BookmarkStatus(BaseModel):
    is_saved: bool


class SavedArticlesResponse(BaseModel):
    results: list[ArticleListItem]
    has_more: bool


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=10000)


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class PasswordResetResponse(BaseModel):
    message: str
