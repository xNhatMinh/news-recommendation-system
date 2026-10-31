import os
import sqlite3
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

with patch.dict(
    os.environ,
    {
        "MYSQL_USER": "test",
        "MYSQL_PASSWORD": "test",
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "test",
    },
):
    from src.api.routes import bookmarks


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={
                "check_same_thread": False,
                "detect_types": sqlite3.PARSE_DECLTYPES,
            },
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys=ON"))
            c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            c.execute(text("INSERT INTO users VALUES (1),(2)"))
            c.execute(text("""CREATE TABLE articles (
                id INTEGER PRIMARY KEY, title TEXT, description TEXT, category TEXT,
                main_category TEXT, url TEXT UNIQUE, image_url TEXT, published_at TIMESTAMP
            )"""))
            c.execute(text("""CREATE TABLE user_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL,
                UNIQUE(user_id,article_id)
            )"""))
        item = patch.object(bookmarks, "engine", self.engine)
        item.start()
        self.addCleanup(item.stop)
        self.user_id = 1
        self.app = FastAPI()
        self.app.include_router(bookmarks.router)
        self.app.dependency_overrides[bookmarks.get_me] = lambda: {
            "user_id": self.user_id
        }
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def add_article(self, article_id):
        url = f"https://news.example/{article_id}?source=app&test=1"
        with self.engine.begin() as c:
            c.execute(
                text("""INSERT INTO articles VALUES (
                :id,:title,NULL,'AI','Công nghệ',:url,'https://images.example/cover.jpg',:date
            )"""),
                {
                    "id": article_id,
                    "title": f"Article {article_id}",
                    "url": url,
                    "date": "2026-10-30 10:00:00",
                },
            )
        return url

    def save(self, url):
        result = self.client.put("/bookmarks", json={"url": url})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"is_saved": True})

    def status(self, url):
        response = self.client.get("/bookmarks/status", params={"url": url})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["is_saved"]

    def page(self, **params):
        response = self.client.get("/bookmarks", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_all_endpoints_require_login(self):
        self.app.dependency_overrides.clear()
        for method, path, kwargs in (
            ("get", "/bookmarks", {}),
            ("get", "/bookmarks/status", {"params": {"url": "https://news.example/1"}}),
            ("put", "/bookmarks", {"json": {"url": "https://news.example/1"}}),
            ("delete", "/bookmarks", {"params": {"url": "https://news.example/1"}}),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(
                    getattr(self.client, method)(path, **kwargs).status_code, 401
                )

    def test_empty_list_and_status(self):
        url = self.add_article(1)
        self.assertFalse(self.status(url))
        self.assertFalse(self.status("https://news.example/missing"))
        self.assertEqual(self.page(), {"results": [], "has_more": False})

    def test_save_is_persistent_and_repeated_save_does_not_duplicate_or_change_order(
        self,
    ):
        first = self.add_article(1)
        second = self.add_article(2)
        self.save(first)
        self.save(second)
        self.save(first)
        self.assertTrue(self.status(first))
        page = self.page()
        self.assertEqual([a["url"] for a in page["results"]], [second, first])
        self.assertFalse(page["has_more"])
        with self.engine.connect() as c:
            self.assertEqual(
                c.execute(text("SELECT COUNT(*) FROM user_bookmarks")).scalar(), 2
            )
        # Một client mới vẫn đọc được dữ liệu đã lưu trong database.
        with TestClient(self.app) as new_client:
            self.assertTrue(
                new_client.get("/bookmarks/status", params={"url": first}).json()[
                    "is_saved"
                ]
            )

    def test_list_and_remove_are_isolated_between_accounts(self):
        shared = self.add_article(1)
        private = self.add_article(2)
        self.save(shared)
        self.save(private)
        self.user_id = 2
        self.assertFalse(self.status(shared))
        self.assertEqual(self.page()["results"], [])
        self.save(shared)
        response = self.client.delete("/bookmarks", params={"url": private})
        self.assertEqual(response.json(), {"is_saved": False})
        self.assertEqual([a["url"] for a in self.page()["results"]], [shared])
        self.user_id = 1
        self.assertTrue(self.status(private))
        self.client.delete("/bookmarks", params={"url": shared})
        self.assertFalse(self.status(shared))
        self.user_id = 2
        self.assertTrue(self.status(shared))

    def test_remove_and_resave_moves_article_to_top(self):
        first = self.add_article(1)
        second = self.add_article(2)
        self.save(first)
        self.save(second)
        for _ in range(2):
            response = self.client.delete("/bookmarks", params={"url": first})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"is_saved": False})
        self.assertFalse(self.status(first))
        self.assertEqual([a["url"] for a in self.page()["results"]], [second])
        self.save(first)
        self.assertEqual([a["url"] for a in self.page()["results"]], [first, second])

    def test_unknown_article_cannot_be_saved_and_remove_is_idempotent(self):
        url = "https://news.example/unknown"
        self.assertEqual(
            self.client.put("/bookmarks", json={"url": url}).status_code, 404
        )
        self.assertEqual(
            self.client.delete("/bookmarks", params={"url": url}).json(),
            {"is_saved": False},
        )
        self.assertEqual(self.page()["results"], [])

    def test_pagination_and_article_fields(self):
        urls = []
        for article_id in range(1, 24):
            url = self.add_article(article_id)
            urls.append(url)
            self.save(url)
        first = self.page()
        last = self.page(offset=20)
        self.assertEqual(len(first["results"]), 20)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(last["results"]), 3)
        self.assertFalse(last["has_more"])
        found = [a["url"] for p in (first, last) for a in p["results"]]
        self.assertEqual(found, list(reversed(urls)))
        self.assertEqual(self.page(offset=23)["results"], [])
        item = first["results"][0]
        self.assertEqual(item["category"], "Công nghệ")
        self.assertEqual(item["description"], "")
        self.assertEqual(item["image_url"], "https://images.example/cover.jpg")
        self.assertEqual(
            set(item),
            {"title", "description", "category", "url", "image_url", "published_at"},
        )

    def test_invalid_input_is_rejected(self):
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            self.assertEqual(
                self.client.get("/bookmarks", params=params).status_code, 422
            )
        for url in ("", "x" * 2049):
            for method, path, kwargs in (
                ("get", "/bookmarks/status", {"params": {"url": url}}),
                ("put", "/bookmarks", {"json": {"url": url}}),
                ("delete", "/bookmarks", {"params": {"url": url}}),
            ):
                self.assertEqual(
                    getattr(self.client, method)(path, **kwargs).status_code, 422
                )
        self.assertEqual(self.client.put("/bookmarks", json={}).status_code, 422)

    def test_deleted_article_and_deleted_account_remove_related_bookmarks(self):
        first = self.add_article(1)
        second = self.add_article(2)
        self.save(first)
        self.save(second)
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM articles WHERE id=1"))
        self.assertFalse(self.status(first))
        self.assertEqual(len(self.page()["results"]), 1)
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE id=1"))
            self.assertEqual(
                c.execute(text("SELECT COUNT(*) FROM user_bookmarks")).scalar(), 0
            )


if __name__ == "__main__":
    unittest.main()
