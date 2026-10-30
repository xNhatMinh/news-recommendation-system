import contextlib
import io
import os
import sqlite3
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

model_stub = types.ModuleType("sentence_transformers")
model_stub.SentenceTransformer = lambda *args, **kwargs: types.SimpleNamespace(
    encode=lambda values: [[1.0, 0.0]]
)
sender_stub = types.ModuleType("src.notifications.sender")
sender_stub.send_notification_to_user = Mock(return_value=0)
originals = {
    key: sys.modules.get(key)
    for key in ("sentence_transformers", "src.notifications.sender")
}
sys.modules["sentence_transformers"] = model_stub
sys.modules["src.notifications.sender"] = sender_stub
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
    from src.api.routes import notifications
    from src.notifications import service, store
for key, value in originals.items():
    if value is None:
        sys.modules.pop(key, None)
    else:
        sys.modules[key] = value


class NotificationTests(unittest.TestCase):
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
            c.execute(
                text(
                    "CREATE TABLE articles (id INTEGER PRIMARY KEY,title TEXT,description TEXT,url TEXT UNIQUE,image_url TEXT,main_category TEXT,published_at TIMESTAMP)"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE user_preferences (id INTEGER PRIMARY KEY,user_id INTEGER,topic TEXT,weight FLOAT)"
                )
            )
            c.execute(
                text(
                    "CREATE TABLE user_notifications (id INTEGER PRIMARY KEY,user_id INTEGER,article_id INTEGER,topic TEXT,is_read BOOLEAN,created_at TIMESTAMP,UNIQUE(user_id,article_id))"
                )
            )
        for module in (notifications, service, store):
            item = patch.object(module, "engine", self.engine)
            item.start()
            self.addCleanup(item.stop)
        self.user_id = 1
        app = FastAPI()
        app.include_router(notifications.router)
        self.app = app
        app.dependency_overrides[notifications.get_me] = lambda: {
            "user_id": self.user_id
        }
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def add_article(self, article_id, topic="Thể thao", description=None):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO articles VALUES (:id,:title,:description,:url,:image,:topic,:date)"
                ),
                {
                    "id": article_id,
                    "title": f"Article {article_id}",
                    "description": description,
                    "url": f"https://news.example/{article_id}",
                    "image": "https://images.example/cover.jpg",
                    "topic": topic,
                    "date": "2026-10-27 10:00:00",
                },
            )

    def save(self, article_id, user_id=1, topic="Thể thao"):
        return store.save_notification(
            user_id, f"https://news.example/{article_id}", topic
        )

    def get(self, **params):
        response = self.client.get("/notifications", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_authentication_required(self):
        self.app.dependency_overrides.clear()
        for method, url in [
            ("get", "/notifications"),
            ("get", "/notifications/unread-count"),
            ("patch", "/notifications/read-all"),
            ("patch", "/notifications/1/read"),
        ]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 401)

    def test_empty_inbox(self):
        self.assertEqual(
            self.get(),
            {"total_count": 0, "unread_count": 0, "results": [], "has_more": False},
        )

    def test_list_counts_paging_filter_and_user_isolation(self):
        for article_id in range(1, 5):
            self.add_article(article_id)
            self.save(article_id, user_id=2 if article_id == 4 else 1)
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE user_notifications SET is_read=1 WHERE user_id=1 AND article_id=2"
                )
            )
        first = self.get(limit=1)
        second = self.get(limit=1, offset=1)
        self.assertEqual(first["total_count"], 3)
        self.assertEqual(first["unread_count"], 2)
        self.assertEqual(first["results"][0]["title"], "Article 3")
        self.assertEqual(second["results"][0]["title"], "Article 2")
        self.assertTrue(second["results"][0]["is_read"])
        self.assertTrue(first["has_more"])
        unread = self.get(unread_only=True)
        self.assertEqual(
            [r["title"] for r in unread["results"]], ["Article 3", "Article 1"]
        )
        self.assertTrue(all(r["is_read"] is False for r in unread["results"]))
        self.assertEqual(unread["results"][0]["description"], "")
        self.assertEqual(unread["total_count"], 3)
        self.assertFalse(unread["has_more"])

    def test_read_one_is_persistent_idempotent_and_private(self):
        self.add_article(1)
        self.save(1)
        self.save(1, user_id=2)
        item = self.get()["results"][0]
        for _ in range(2):
            response = self.client.patch(f'/notifications/{item["id"]}/read')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["unread_count"], 0)
        self.assertTrue(self.get()["results"][0]["is_read"])
        self.assertEqual(self.get(unread_only=True)["results"], [])
        self.user_id = 2
        self.assertEqual(
            self.client.patch(f'/notifications/{item["id"]}/read').status_code, 404
        )
        self.assertEqual(
            self.client.patch("/notifications/99999/read").status_code, 404
        )
        self.assertEqual(
            self.client.get("/notifications/unread-count").json()["unread_count"], 1
        )

    def test_read_all_covers_all_pages_and_only_current_user(self):
        for article_id in range(1, 24):
            self.add_article(article_id)
            self.save(article_id)
        self.save(1, user_id=2)
        self.assertTrue(self.get()["has_more"])
        response = self.client.patch("/notifications/read-all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"total_count": 23, "unread_count": 0})
        self.assertEqual(self.get(unread_only=True)["results"], [])
        self.user_id = 2
        self.assertEqual(
            self.client.get("/notifications/unread-count").json()["unread_count"], 1
        )

    def test_retry_does_not_duplicate_or_reset_read_state(self):
        self.add_article(1)
        self.assertTrue(self.save(1))
        self.client.patch("/notifications/read-all")
        self.assertFalse(self.save(1, topic="Messi"))
        data = self.get()
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["unread_count"], 0)
        self.assertEqual(data["results"][0]["topic"], "Thể thao")

    def test_invalid_paging(self):
        for params in [
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
            {"unread_only": "bad"},
        ]:
            self.assertEqual(
                self.client.get("/notifications", params=params).status_code, 422
            )

    def test_main_topic_matches_without_embedding_score(self):
        rows = [
            {"url": "one", "main_category": "Thể thao"},
            {"url": "two", "main_category": "Du lịch"},
        ]
        with patch.object(service, "search_hybrid") as search:
            self.assertEqual(
                service.find_matching_articles("Thể thao", rows), [rows[0]]
            )
            search.assert_not_called()

    def test_keyword_still_requires_relevance_and_only_checks_new_urls(self):
        rows = [
            {"url": "one", "published_at": datetime(2026, 10, 27)},
            {"url": "two", "published_at": datetime(2026, 10, 27)},
        ]
        results = [
            {"url": "one", "hybrid_score": 0.8},
            {"url": "two", "hybrid_score": 0.1},
        ]
        with patch.object(service, "search_hybrid", return_value=results) as search:
            self.assertEqual(
                service.find_matching_articles("Messi", rows), [results[0]]
            )
            self.assertEqual(search.call_args.kwargs["article_urls"], {"one", "two"})

    def test_pipeline_saves_without_device_and_deduplicates_overlapping_preferences(
        self,
    ):
        self.add_article(1)
        article = {
            "url": "https://news.example/1",
            "main_category": "Thể thao",
            "published_at": datetime(2026, 10, 27),
        }
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO user_preferences VALUES (1,1,'Messi',1.0),(2,1,'Thể thao',1.0)"
                )
            )
        with patch.object(
            service, "search_hybrid", return_value=[{**article, "hybrid_score": 0.9}]
        ), patch.object(
            service, "send_notification_to_user", return_value=0
        ) as push, contextlib.redirect_stdout(
            io.StringIO()
        ):
            service.notify_new_articles([article])
            service.notify_new_articles([article])
            push.assert_called_once()
            self.assertEqual(push.call_args.kwargs["data"], {"screen": "notifications"})
        data = self.get()
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["results"][0]["topic"], "Thể thao")

    def test_failed_push_does_not_lose_persisted_notification(self):
        self.add_article(1)
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO user_preferences VALUES (1,1,'Thể thao',1.0)"))
        article = {"url": "https://news.example/1", "main_category": "Thể thao"}
        with patch.object(
            service, "send_notification_to_user", side_effect=RuntimeError("offline")
        ), contextlib.redirect_stdout(io.StringIO()):
            service.notify_new_articles([article])
        self.assertEqual(self.get()["unread_count"], 1)


if __name__ == "__main__":
    unittest.main()
