"""Admin page and JSON API. Uses the existing JWT and update job."""
import os
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import text

from src.api.security import create_access_token, get_token_payload, verify_admin_password
from src.api.routes.automation import start_update, update_status
from src.db.db import engine
from src.db.admin_store import SOURCES, get_sources, set_source_enabled, set_article_hidden, set_user_active

router = APIRouter(prefix="/admin", tags=["Admin"])
login_attempts = {}
login_lock = Lock()


def get_admin(payload=Depends(get_token_payload)):
    username = os.getenv("ADMIN_USERNAME", "")
    if not username or payload.get("role") != "admin" or payload.get("sub") != f"admin:{username}":
        raise HTTPException(403, "Tài khoản không có quyền quản trị")
    return username


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class SourceUpdate(BaseModel):
    enabled: StrictBool


class RunUpdate(BaseModel):
    sources: list[str] | None = None


class ArticleUpdate(BaseModel):
    hidden: StrictBool


class UserUpdate(BaseModel):
    is_active: StrictBool


@router.get("", include_in_schema=False)
def admin_page():
    return FileResponse(Path(__file__).with_name("admin.html"), headers={"Cache-Control": "no-store"})


@router.post("/login")
def admin_login(data: AdminLogin, request: Request):
    if not os.getenv("ADMIN_USERNAME") or not os.getenv("ADMIN_PASSWORD_HASH"):
        raise HTTPException(503, "Chưa cấu hình tài khoản admin")
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with login_lock:
        # Expire old entries and limit failed attempts without another dependency.
        for key in list(login_attempts):
            if now - login_attempts[key][0] >= 300:
                del login_attempts[key]
        since, attempts = login_attempts.get(ip, (now, 0))
        if attempts >= 5:
            raise HTTPException(429, "Đăng nhập sai nhiều lần. Hãy thử lại sau 5 phút.")
        login_attempts[ip] = (since, attempts + 1)
    password_ok = verify_admin_password(data.password, os.getenv("ADMIN_PASSWORD_HASH", ""))
    if data.username != os.getenv("ADMIN_USERNAME") or not password_ok:
        raise HTTPException(401, "Username hoặc mật khẩu không đúng")
    with login_lock:
        login_attempts.pop(ip, None)
    return {"username": data.username, "access_token": create_access_token(f"admin:{data.username}", role="admin"),
            "token_type": "bearer"}


@router.get("/overview")
def overview(admin=Depends(get_admin)):
    with engine.connect() as connection:
        total = connection.execute(text("SELECT COUNT(*) FROM articles")).scalar()
        hidden = connection.execute(text("SELECT COUNT(*) FROM hidden_articles")).scalar()
        users = connection.execute(text('''
            SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END), 0) AS locked
            FROM users
        ''')).mappings().one()
    return {"username": admin, "total_articles": total, "hidden_articles": hidden,
            "total_users": users['total'], "locked_users": users['locked'],
            "sources": get_sources(), "job": update_status()}


@router.get('/users')
def users(q: str = Query('', max_length=200), account_status: str = 'all',
          limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
          admin=Depends(get_admin)):
    if account_status not in ('all', 'active', 'locked'):
        raise HTTPException(422, 'Trạng thái tài khoản không hợp lệ')
    where = ' WHERE 1=1'
    params = {'limit': limit + 1, 'offset': offset}
    if q.strip():
        where += ' AND (LOWER(username) LIKE LOWER(:q) OR LOWER(email) LIKE LOWER(:q))'
        params['q'] = f'%{q.strip()}%'
    if account_status != 'all':
        where += ' AND is_active = :active'
        params['active'] = account_status == 'active'
    with engine.connect() as connection:
        count = connection.execute(text('SELECT COUNT(*) FROM users' + where), params).scalar()
        rows = connection.execute(text('SELECT id, username, email, created_at, is_active FROM users'
                                       + where + ' ORDER BY id DESC LIMIT :limit OFFSET :offset'), params).mappings().all()
    return {'results': [{**dict(row), 'is_active': bool(row['is_active'])} for row in rows[:limit]],
            'has_more': len(rows) > limit, 'total_count': count}


@router.patch('/users/{user_id}')
def change_user(user_id: int, data: UserUpdate, admin=Depends(get_admin)):
    if not set_user_active(user_id, data.is_active):
        raise HTTPException(404, 'Không tìm thấy người dùng')
    return {'id': user_id, 'is_active': data.is_active}


@router.patch("/sources/{code}")
def change_source(code: str, data: SourceUpdate, admin=Depends(get_admin)):
    if code not in SOURCES:
        raise HTTPException(404, "Nguồn tin không tồn tại")
    set_source_enabled(code, data.enabled)
    return {"code": code, "enabled": data.enabled}


@router.post("/update-news", status_code=202)
def run_news_update(data: RunUpdate, tasks: BackgroundTasks, admin=Depends(get_admin)):
    return start_update(tasks, data.sources)


@router.get("/update-news/status")
def news_update_status(admin=Depends(get_admin)):
    return update_status()


@router.get("/articles")
def articles(q: str = Query("", max_length=200), source: str | None = None,
             visibility: str = "all", limit: int = Query(20, ge=1, le=100),
             offset: int = Query(0, ge=0), admin=Depends(get_admin)):
    sql = """SELECT a.id, a.title, a.url, a.published_at,
             COALESCE(NULLIF(a.main_category, ''), a.category) AS category,
             CASE WHEN h.article_id IS NULL THEN 0 ELSE 1 END AS hidden
             FROM articles a LEFT JOIN hidden_articles h ON h.article_id = a.id WHERE 1=1"""
    params = {"limit": limit+1, "offset": offset}
    if q.strip():
        sql += " AND a.title LIKE :q"
        params["q"] = f"%{q.strip()}%"
    if source is not None:
        if source not in SOURCES:
            raise HTTPException(422, "Nguồn tin không hợp lệ")
        sql += " AND a.url LIKE :prefix"
        params["prefix"] = f"https://{SOURCES[source][1]}/%"
    if visibility not in ("all", "visible", "hidden"):
        raise HTTPException(422, "Trạng thái không hợp lệ")
    if visibility != "all":
        sql += " AND h.article_id IS " + ("NOT NULL" if visibility == "hidden" else "NULL")
    sql += " ORDER BY a.published_at DESC, a.id DESC LIMIT :limit OFFSET :offset"
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return {"results": [dict(row) for row in rows[:limit]], "has_more": len(rows)>limit}


@router.get("/articles/{article_id}")
def preview_article(article_id: int, admin=Depends(get_admin)):
    with engine.connect() as connection:
        row = connection.execute(text("SELECT id, title, content, url FROM articles WHERE id = :id"),
                                 {"id": article_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài viết")
    return dict(row)


@router.patch("/articles/{article_id}")
def change_article(article_id: int, data: ArticleUpdate, admin=Depends(get_admin)):
    if not set_article_hidden(article_id, data.hidden):
        raise HTTPException(404, "Không tìm thấy bài viết")
    return {"id": article_id, "hidden": data.hidden}
