import os
import sqlite3
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# Không tải model hoặc kết nối MySQL thật khi chạy kiểm thử.
original = sys.modules.get("sentence_transformers")
stub = types.ModuleType("sentence_transformers")
stub.SentenceTransformer = Mock(return_value=types.SimpleNamespace(encode=Mock()))
sys.modules["sentence_transformers"] = stub
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
    from src.api.routes import search
    from src.embedding import hybrid_search
if original is None:
    sys.modules.pop("sentence_transformers", None)
else:
    sys.modules["sentence_transformers"] = original


class ArticleSearchTests(unittest.TestCase):
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
            c.execute(text("""CREATE TABLE articles (
                id INTEGER PRIMARY KEY, title TEXT, description TEXT, content TEXT,
                category TEXT, main_category TEXT, url TEXT, image_url TEXT,
                published_at TIMESTAMP
            )"""))
            c.execute(
                text(
                    "CREATE TABLE article_embeddings (article_id INTEGER, embedding TEXT)"
                )
            )
        for item in (
            patch.object(hybrid_search, "engine", self.engine),
            patch.object(hybrid_search.model, "encode", return_value=[[1.0, 0.0]]),
        ):
            item.start()
            self.addCleanup(item.stop)
        self.app = FastAPI()
        self.app.include_router(search.router)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def add_article(
        self,
        article_id,
        title="Tin khác",
        vector="[1,0]",
        category="Thể thao",
        main_category=None,
        description=None,
        content=None,
    ):
        with self.engine.begin() as c:
            c.execute(
                text("""INSERT INTO articles VALUES (
                :id,:title,:description,:content,:category,:main_category,:url,:image,:published
            )"""),
                {
                    "id": article_id,
                    "title": title,
                    "description": description,
                    "content": content,
                    "category": category,
                    "main_category": main_category,
                    "url": f"https://news.example/{article_id}",
                    "image": "https://image.example/photo.jpg",
                    "published": "2026-01-01 10:00:00",
                },
            )
            if vector is not None:
                c.execute(
                    text("INSERT INTO article_embeddings VALUES (:id,:vector)"),
                    {"id": article_id, "vector": vector},
                )

    def get_page(self, **params):
        response = self.client.get(
            "/articles/search", params={"q": "giá vàng", **params}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_guest_can_search_even_with_expired_token(self):
        self.add_article(1, title="Giá vàng hôm nay")
        for headers in ({}, {"Authorization": "Bearer expired-token"}):
            response = self.client.get(
                "/articles/search", params={"q": "giá vàng"}, headers=headers
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["results"]), 1)

    def test_keyword_and_semantic_matches_are_ranked_and_irrelevant_results_removed(
        self,
    ):
        self.add_article(1, title="GIÁ VÀNG hôm nay", vector="[0,1]")
        self.add_article(2, title="Kim loại quý tăng mạnh", vector="[0.8,0.6]")
        self.add_article(3, title="Bóng đá", vector="[0,1]")
        page = self.get_page()
        self.assertEqual(
            [a["title"] for a in page["results"]],
            ["Kim loại quý tăng mạnh", "GIÁ VÀNG hôm nay"],
        )
        self.assertFalse(page["has_more"])
        self.assertEqual(page["results"][0]["description"], "")
        self.assertEqual(
            page["results"][0]["image_url"], "https://image.example/photo.jpg"
        )
        self.assertNotIn("content", page["results"][0])
        self.assertNotIn("hybrid_score", page["results"][0])

    def test_pagination_filters_before_slicing_and_has_stable_ties(self):
        for i in range(1, 6):
            self.add_article(i)
        self.add_article(6, vector="[0,1]")
        first = self.get_page(limit=2)
        second = self.get_page(limit=2, offset=2)
        last = self.get_page(limit=2, offset=4)
        beyond = self.get_page(limit=2, offset=6)
        urls = [a["url"] for page in (first, second, last) for a in page["results"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len(urls), 5)
        self.assertTrue(first["has_more"])
        self.assertTrue(second["has_more"])
        self.assertFalse(last["has_more"])
        self.assertEqual(beyond["results"], [])

    def test_main_topic_includes_child_sections_without_semantic_threshold(self):
        self.add_article(1, category="AI", main_category="Công nghệ", vector="[0,1]")
        self.add_article(
            2, category="Thiết bị", main_category="Công nghệ", vector="[0,1]"
        )
        self.add_article(3, category="Vũ trụ", main_category="Khoa học")
        page = self.get_page(q="Công nghệ")
        self.assertEqual(len(page["results"]), 2)
        self.assertTrue(all(a["category"] == "Công nghệ" for a in page["results"]))

    def test_normalizes_query_and_matches_full_content(self):
        self.add_article(1, content="Thông tin về giá vàng", vector="[0,1]")
        page = self.get_page(q="  giá   vàng  ")
        self.assertEqual(len(page["results"]), 1)
        hybrid_search.model.encode.assert_called_once_with(["giá vàng"])

    def test_empty_database_and_no_matches(self):
        self.assertEqual(self.get_page(), {"results": [], "has_more": False})
        self.add_article(1, vector="[0,1]")
        self.assertEqual(self.get_page(), {"results": [], "has_more": False})

    def test_rejects_invalid_queries_and_pagination(self):
        for params in (
            {"q": ""},
            {"q": "   "},
            {"q": "x" * 201},
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    "/articles/search", params={"q": "tin", **params}
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/articles/search").status_code, 422)


if __name__ == "__main__":
    unittest.main()
