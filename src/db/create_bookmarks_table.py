"""Tạo bảng lưu bài: python -m src.db.create_bookmarks_table."""

from pathlib import Path
from sqlalchemy import text
from src.db.db import engine


def create_bookmarks_table():
    sql = Path(__file__).with_name("user_bookmarks.sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.execute(text(sql))


if __name__ == "__main__":
    create_bookmarks_table()
    print("Bookmarks table is ready.")
