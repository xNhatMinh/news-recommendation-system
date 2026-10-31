"""Tạo liên kết Firebase: python -m src.db.create_firebase_accounts_table."""

from sqlalchemy import text
from src.db.db import engine


def create_firebase_accounts_table():
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS user_firebase_accounts (
                user_id BIGINT NOT NULL PRIMARY KEY,
                firebase_uid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_firebase_uid UNIQUE (firebase_uid),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))


if __name__ == "__main__":
    create_firebase_accounts_table()
    print("Firebase accounts table is ready.")
