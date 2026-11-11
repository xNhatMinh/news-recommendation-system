import logging
import os
from secrets import compare_digest
from threading import Lock

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from src.update_news import main as run_update
from src.db.admin_store import SOURCES, get_sources

load_dotenv()
logger = logging.getLogger(__name__)
update_lock = Lock()
job = {"status": "idle", "message": "Chưa chạy cập nhật"}


def check_key(x_update_key: str | None = Header(default=None, alias="X-Update-Key")):
    expected_key = os.getenv("N8N_KEY")
    if not expected_key:
        raise HTTPException(503, "Chưa cấu hình N8N_KEY")
    if not compare_digest((x_update_key or "").encode(), expected_key.encode()):
        raise HTTPException(401, "Khóa xác thực không hợp lệ")


router = APIRouter(
    prefix="/internal", tags=["Automation"], dependencies=[Depends(check_key)]
)


def run_in_background(sources=None):
    try:
        report = run_update(sources=sources)
    except Exception:
        logger.exception("Lượt cập nhật tin gặp lỗi")
        result = {"status": "failed", "message": "Cập nhật gặp lỗi, kiểm tra log backend"}
    else:
        result = {"status": report["status"], "message": "Đã chạy xong lượt cập nhật",
                  "new_articles": report["new_articles"], "results": report["sources"]}
    with update_lock:
        job.update(result)


def start_update(background_tasks: BackgroundTasks, sources=None):
    enabled = {row["code"] for row in get_sources() if row["enabled"]}
    if sources is not None:
        if not sources or any(code not in SOURCES or code not in enabled for code in sources):
            raise HTTPException(400, "Hãy chọn nguồn đang được bật")
        sources = list(dict.fromkeys(sources))
    elif not enabled:
        return {"status": "skipped", "message": "Tất cả nguồn tin đang tắt"}
    with update_lock:
        if job["status"] == "running":
            return {"status": "skipped", "message": "Đang có lượt cập nhật chạy"}
        job.clear()
        job.update(status="running", message="Backend đang cập nhật tin")
    background_tasks.add_task(run_in_background, sources)
    return {"status": "accepted", "message": "Đã nhận yêu cầu cập nhật tin"}


@router.post("/update-news", status_code=202)
def update_news(background_tasks: BackgroundTasks):
    return start_update(background_tasks)


@router.get("/update-news/status")
def update_status():
    with update_lock:
        return dict(job)
