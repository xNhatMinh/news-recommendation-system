from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.auth import router as auth_router
from src.api.routes.recommendation import router as recommendation_router
from src.api.routes.preferences import router as preferences_router
from src.api.routes.history import router as history_router
from src.api.routes.summary import router as summary_router
from src.api.routes.devices import router as devices_router
from src.api.routes.articles import router as articles_router
from src.api.routes.search import router as search_router
from src.api.routes.bookmarks import router as bookmarks_router
from src.api.routes.notifications import router as notifications_router
from src.api.routes.automation import router as automation_router
from src.api.routes.terms import router as terms_router
from src.api.routes.admin import router as admin_router
from src.db.admin_store import init_admin_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_admin_tables()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="News Recommendation API",
    description="API for personalized news recommendation",
    version="1.0.0",
)


app.include_router(auth_router)
app.include_router(recommendation_router)
app.include_router(preferences_router)
app.include_router(history_router)
app.include_router(summary_router)
app.include_router(devices_router)
app.include_router(articles_router)
app.include_router(search_router)
app.include_router(bookmarks_router)
app.include_router(notifications_router)
app.include_router(automation_router)

app.include_router(terms_router)
app.include_router(admin_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
