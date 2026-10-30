"""Tạo bảng hộp thông báo: python -m src.db.create_notifications_table."""

from sqlalchemy import text
from src.db.db import engine


def create_notifications_table():
    sql = text("""
        CREATE TABLE IF NOT EXISTS user_notifications (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            article_id BIGINT NOT NULL,
            topic VARCHAR(200) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_notification_user_article UNIQUE (user_id, article_id),
            INDEX idx_notification_user_read (user_id, is_read, id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    with engine.begin() as connection:
        connection.execute(sql)


if __name__ == "__main__":
    create_notifications_table()
    print("Notification table is ready.")
