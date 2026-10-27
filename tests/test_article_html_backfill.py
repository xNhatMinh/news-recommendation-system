import contextlib
import io
import os
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

with patch.dict(os.environ, {
    "MYSQL_USER": "test",
    "MYSQL_PASSWORD": "test",
    "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306",
    "MYSQL_DATABASE": "test",
}):
    from src.crawler import backfill_article_html as backfill


ARTICLE_HTML = """
<article class="fck_detail">
    <p class="Normal">First paragraph <strong>bold</strong></p>
    <figure>
        <img src="placeholder.gif" data-src="//images.example/first.jpg" onerror="alert(1)">
        <figcaption>First caption</figcaption>
    </figure>
    <p class="Normal">Second paragraph</p>
    <figure>
        <picture>
            <source data-srcset="https://images.example/second-large.jpg 2x">
            <img data-original="/photos/second.jpg" loading="lazy">
        </picture>
        <figcaption>Second caption</figcaption>
    </figure>
    <p class="Normal">Last paragraph</p>
    <script>alert(1)</script>
</article>
"""


class ArticleHtmlBackfillTests(unittest.TestCase):
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
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_html TEXT,
                    published_at TEXT
                )
            """))

        for item in (
            patch.object(backfill, "engine", self.engine),
            patch.object(backfill.time, "sleep"),
            patch.object(backfill, "get_soup", side_effect=lambda _: BeautifulSoup(ARTICLE_HTML, "html.parser")),
        ):
            item.start()
            self.addCleanup(item.stop)

    def add_article(self, article_id, html=None):
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO articles
                    (id, url, title, content, content_html, published_at)
                VALUES (:id, :url, 'Original title', 'Original text', :html, :date)
            """), {
                "id": article_id,
                "url": f"https://news.example/article-{article_id}.html",
                "html": html,
                "date": f"2026-10-{article_id:02d}",
            })

    def run_backfill(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return backfill.backfill_article_html(workers=1, **kwargs)

    def get_article(self, article_id):
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT * FROM articles WHERE id = :id"), {"id": article_id}
            ).mappings().one()

    def test_keeps_both_images_captions_and_order_without_changing_plain_text(self):
        self.add_article(1)
        self.assertEqual(self.run_backfill(), {"updated": 1, "skipped": 0, "failed": 0})
        row = self.get_article(1)
        self.assertEqual(row["title"], "Original title")
        self.assertEqual(row["content"], "Original text")
        body = BeautifulSoup(row["content_html"], "html.parser")
        self.assertEqual(
            [node.name for node in body.find_all(recursive=False)],
            ["p", "figure", "p", "figure", "p"],
        )
        self.assertEqual([img["src"] for img in body.select("img")], [
            "https://images.example/first.jpg",
            "https://news.example/photos/second.jpg",
        ])
        self.assertEqual([caption.get_text() for caption in body.select("figcaption")], [
            "First caption", "Second caption",
        ])
        self.assertIsNotNone(body.select_one("strong"))
        self.assertEqual(body.select_one("source")["srcset"], "https://images.example/second-large.jpg 2x")
        self.assertFalse(body.select("script, [onerror], [loading]"))

    def test_limit_selects_newest_missing_article_and_rerun_skips_completed(self):
        self.add_article(1)
        self.add_article(2)
        self.add_article(3, "<p>Existing HTML</p>")
        self.assertEqual(self.run_backfill(limit=1)["updated"], 1)
        self.assertIsNone(self.get_article(1)["content_html"])
        self.assertTrue(self.get_article(2)["content_html"])
        self.assertEqual(self.get_article(3)["content_html"], "<p>Existing HTML</p>")
        self.assertEqual(self.run_backfill()["updated"], 1)
        self.assertEqual(self.run_backfill()["updated"], 0)

    def test_failed_fetch_and_missing_body_leave_data_untouched_and_continue(self):
        for article_id in (1, 2, 3):
            self.add_article(article_id)

        def fetch(url):
            if "article-3" in url:
                raise TimeoutError("Source unavailable")
            if "article-2" in url:
                return BeautifulSoup("<p>No article body</p>", "html.parser")
            return BeautifulSoup(ARTICLE_HTML, "html.parser")

        with patch.object(backfill, "get_soup", side_effect=fetch):
            self.assertEqual(self.run_backfill(), {"updated": 1, "skipped": 1, "failed": 1})
        self.assertIsNone(self.get_article(3)["content_html"])
        self.assertIsNone(self.get_article(2)["content_html"])
        self.assertTrue(self.get_article(1)["content_html"])

    def test_does_not_overwrite_html_saved_during_fetch(self):
        self.add_article(1)

        def fetch(_):
            with self.engine.begin() as connection:
                connection.execute(text("UPDATE articles SET content_html = '<p>Concurrent update</p>' WHERE id = 1"))
            return BeautifulSoup(ARTICLE_HTML, "html.parser")

        with patch.object(backfill, "get_soup", side_effect=fetch):
            self.assertEqual(self.run_backfill(), {"updated": 0, "skipped": 1, "failed": 0})
        self.assertEqual(self.get_article(1)["content_html"], "<p>Concurrent update</p>")

    def test_url_option_only_updates_requested_article(self):
        self.add_article(1)
        self.add_article(2)
        self.assertEqual(self.run_backfill(url="https://news.example/article-1.html")["updated"], 1)
        self.assertTrue(self.get_article(1)["content_html"])
        self.assertIsNone(self.get_article(2)["content_html"])


if __name__ == "__main__":
    unittest.main()
