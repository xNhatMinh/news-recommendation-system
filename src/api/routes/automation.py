import logging
import os
from secrets import compare_digest
from threading import Lock

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from src.update_news import main as run_update

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


def run_in_background():
    try:
        run_update()
    except Exception:
        logger.exception("Lượt cập nhật tin gặp lỗi")
        result = {"status": "failed", "message": "Cập nhật gặp lỗi, kiểm tra log backend"}
    else:
        result = {"status": "finished", "message": "Đã chạy xong lượt cập nhật"}
    with update_lock:
        job.update(result)


@router.post("/update-news", status_code=202)
def update_news(background_tasks: BackgroundTasks):
    with update_lock:
        if job["status"] == "running":
            return {"status": "skipped", "message": "Đang có lượt cập nhật chạy"}
        job.update(status="running", message="Backend đang cập nhật tin")
    background_tasks.add_task(run_in_background)
    return {"status": "accepted", "message": "Đã nhận yêu cầu cập nhật tin"}


@router.get("/update-news/status")
def update_status():
    with update_lock:
        return dict(job)
