import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from src.news_topics import MAIN_TOPICS

with patch.dict(os.environ, {
    "MYSQL_USER": "test",
    "MYSQL_PASSWORD": "test",
    "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306",
    "MYSQL_DATABASE": "test",
}):
    from src.api.routes import articles


class LatestArticlesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE articles (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    content TEXT,
                    content_html TEXT,
                    category TEXT,
                    main_category TEXT,
                    url TEXT NOT NULL,
                    image_url TEXT,
                    published_at DATETIME
                )
            """))

        engine_patch = patch.object(articles, "engine", self.engine)
        engine_patch.start()
        self.addCleanup(engine_patch.stop)
        self.app = FastAPI()
        self.app.include_router(articles.router)
        # No user_preferences table: a new reader must still receive latest news.
        self.app.dependency_overrides[articles.get_me] = lambda: {"user_id": 123}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def add_article(self, article_id, date="2026-10-26 10:00:00", category="Thể thao", description=None, main_category=None):
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO articles
                    (id, title, description, content, content_html, category, main_category, url, published_at)
                VALUES
                    (:id, :title, :description, 'Full text', '<p>Full HTML</p>', :category, :main_category, :url, :date)
            """), {
                "id": article_id,
                "title": f"Article {article_id}",
                "description": description,
                "category": category,
                "main_category": main_category,
                "url": f"https://news.example/article-{article_id}.html",
                "date": date,
            })

    def get_page(self, **params):
        response = self.client.get("/articles/latest", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def titles(self, page):
        return [article["title"] for article in page["results"]]

    def test_requires_login(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/articles/latest").status_code, 401)

    def test_new_user_gets_all_topics_in_date_order_with_stable_ties(self):
        self.add_article(1, "2026-10-25 10:00:00", "Thể thao")
        self.add_article(2, "2026-10-26 10:00:00", "Sức khỏe")
        self.add_article(3, "2026-10-26 10:00:00", "Kinh doanh")
        self.add_article(4, None, "Hidden category")
        page = self.get_page()
        self.assertEqual(self.titles(page), ["Article 3", "Article 2", "Article 1"])
        self.assertEqual(page["categories"], MAIN_TOPICS)
        self.assertFalse(page["has_more"])

    def test_pagination_reaches_every_article_without_duplicates(self):
        for article_id in range(1, 6):
            self.add_article(article_id)
        first = self.get_page(limit=2)
        second = self.get_page(limit=2, offset=2)
        last = self.get_page(limit=2, offset=4)
        beyond = self.get_page(limit=2, offset=6)
        self.assertEqual(self.titles(first), ["Article 5", "Article 4"])
        self.assertEqual(self.titles(second), ["Article 3", "Article 2"])
        self.assertEqual(self.titles(last), ["Article 1"])
        self.assertTrue(first["has_more"])
        self.assertTrue(second["has_more"])
        self.assertFalse(last["has_more"])
        self.assertEqual(beyond["results"], [])
        self.assertFalse(beyond["has_more"])

    def test_default_page_has_twenty_articles_and_reports_more(self):
        for article_id in range(1, 22):
            self.add_article(article_id)
        page = self.get_page()
        self.assertEqual(len(page["results"]), 20)
        self.assertTrue(page["has_more"])

    def test_category_filters_whole_database_and_keeps_global_category_choices(self):
        self.add_article(1, "2026-10-24 10:00:00", "Thể thao")
        self.add_article(2, "2026-10-25 10:00:00", "Thể thao")
        self.add_article(3, "2026-10-26 10:00:00", "Kinh doanh")
        self.add_article(4, category=None)
        self.add_article(5, category="   ")
        first = self.get_page(category="Thể thao", limit=1)
        second = self.get_page(category="Thể thao", limit=1, offset=1)
        self.assertEqual(self.titles(first), ["Article 2"])
        self.assertEqual(self.titles(second), ["Article 1"])
        self.assertEqual(first["categories"], MAIN_TOPICS)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])

    def test_empty_database_keeps_main_topic_choices(self):
        self.assertEqual(self.get_page(), {"results": [], "categories": MAIN_TOPICS, "has_more": False})

    def test_main_topic_includes_child_sections_in_date_order(self):
        self.add_article(1, category="AI", main_category="Công nghệ")
        self.add_article(2, category="Thiết bị", main_category="Công nghệ")
        self.add_article(3, category="Vũ trụ", main_category="Khoa học")
        first = self.get_page(category="Công nghệ", limit=1)
        second = self.get_page(category="Công nghệ", limit=1, offset=1)
        self.assertEqual(self.titles(first), ["Article 2"])
        self.assertEqual(self.titles(second), ["Article 1"])
        self.assertEqual(first["results"][0]["category"], "Công nghệ")
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertNotIn("AI", first["categories"])

    def test_shared_child_name_does_not_mix_main_topics(self):
        self.add_article(1, category="Tin tức", main_category="Sức khỏe")
        self.add_article(2, category="Tin tức", main_category="Giáo dục")
        page = self.get_page(category="Sức khỏe")
        self.assertEqual(self.titles(page), ["Article 1"])
        self.assertEqual(page["categories"], MAIN_TOPICS)

    def test_unknown_category_has_no_results(self):
        self.add_article(1)
        page = self.get_page(category="Unknown")
        self.assertEqual(page["results"], [])
        self.assertFalse(page["has_more"])

    def test_rejects_invalid_pagination_and_empty_category(self):
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"category": ""}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/articles/latest", params=params).status_code, 422)

    def test_list_normalizes_null_description_and_does_not_send_full_article(self):
        self.add_article(1)
        article = self.get_page()["results"][0]
        self.assertEqual(article["description"], "")
        self.assertIsNone(article["image_url"])
        self.assertEqual(article["published_at"], "2026-10-26T10:00:00")
        self.assertEqual(set(article), {"title", "description", "category", "url", "image_url", "published_at"})


if __name__ == "__main__":
    unittest.main()
