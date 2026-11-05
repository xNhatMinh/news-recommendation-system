"""Các thao tác lưu bài viết dùng chung cho các nguồn báo."""

from sqlalchemy import text


def article_exists(connection, url):
    return connection.execute(
        text("SELECT id FROM articles WHERE url = :url LIMIT 1"), {"url": url}
    ).first() is not None


def insert_article(connection, article):
    connection.execute(
        text("""
            INSERT INTO articles (
                title, description, content, content_html, category,
                main_category, url, image_url, published_at
            ) VALUES (
                :title, :description, :content, :content_html, :category,
                :main_category, :url, :image_url, :published_at
            )
        """),
        {
            "title": article["title"],
            "description": article["description"],
            "content": article["content"],
            "content_html": article.get("content_html", ""),
            "category": article["category"],
            "main_category": article.get("main_category"),
            "url": article["url"],
            "image_url": article.get("image_url"),
            "published_at": article["published_at"],
        },
    )
