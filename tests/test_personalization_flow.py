import contextlib
import json
import os
import sqlite3
import sys
import types
import unittest
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from src.news_topics import MAIN_TOPICS

# Chạy luồng thật với database thử, không tải mô hình hay gọi Gemini.
model_stub = types.ModuleType('sentence_transformers')
model_stub.SentenceTransformer = lambda *a, **k: types.SimpleNamespace(encode=lambda values: [[1.0, 0.0]])
previous_model_module = sys.modules.get('sentence_transformers')
sys.modules['sentence_transformers'] = model_stub
with patch.dict(os.environ, {
    'MYSQL_USER': 'test', 'MYSQL_PASSWORD': 'test', 'MYSQL_HOST': 'localhost',
    'MYSQL_PORT': '3306', 'MYSQL_DATABASE': 'test', 'GEMINI_API_KEY': 'test-key',
}):
    from src.embedding import hybrid_search
    from src.recommendation import user_profile, history
    from src.api.routes import preferences, recommendation, summary
if previous_model_module is None:
    sys.modules.pop('sentence_transformers', None)
else:
    sys.modules['sentence_transformers'] = previous_model_module


class PersonalizationFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={
            'check_same_thread': False, 'detect_types': sqlite3.PARSE_DECLTYPES,
        }, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.execute(text('CREATE TABLE user_preferences (user_id INTEGER,topic TEXT,weight FLOAT,UNIQUE(user_id,topic))'))
            c.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY,title TEXT,description TEXT,content TEXT,category TEXT,main_category TEXT,url TEXT,image_url TEXT,published_at TIMESTAMP)'))
            c.execute(text('CREATE TABLE article_embeddings (article_id INTEGER PRIMARY KEY,embedding TEXT)'))
            c.execute(text('CREATE TABLE recommendation_history (user_id INTEGER,article_id INTEGER,score FLOAT)'))
        for module in (hybrid_search, user_profile, history):
            patcher = patch.object(module, 'engine', self.engine)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(hybrid_search, 'model', types.SimpleNamespace(encode=lambda values: [[1.0, 0.0]]))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user_id = 1
        self.app = FastAPI()
        for router in (preferences.router, recommendation.router, summary.router):
            self.app.include_router(router)
        self.app.dependency_overrides[preferences.get_me] = lambda: {'user_id': self.user_id}
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.window = {'start_date': '2026-10-01', 'end_date': '2026-10-27'}

    def add_article(self, article_id, topic, content='Neutral content', vector=None):
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO articles VALUES (:id,:title,:description,:content,:child,:topic,:url,:image,:date)'), {
                'id': article_id, 'title': f'Article {article_id}', 'description': '',
                'content': content, 'child': 'Child section', 'topic': topic,
                'url': f'https://news.example/{article_id}', 'image': 'https://images.example/cover.jpg',
                'date': '2026-10-26 10:00:00',
            })
            c.execute(text('INSERT INTO article_embeddings VALUES (:id,:embedding)'), {
                'id': article_id, 'embedding': json.dumps(vector if vector is not None else [0.0, 1.0]),
            })

    def save(self, topics):
        response = self.client.put('/preferences', json={'topics': topics})
        self.assertEqual(response.status_code, 200, response.text)

    def recommendations(self):
        response = self.client.post('/recommend', json=self.window)
        self.assertEqual(response.status_code, 200, response.text)
        return [row['url'] for row in response.json()['results']]

    def test_save_reopen_and_remove_topics_keeps_keywords_and_other_user(self):
        self.save(['Thể thao', 'Du lịch', 'Messi'])
        response = self.client.get('/preferences')
        self.assertEqual({p['topic'] for p in response.json()['preferences']}, {'Thể thao', 'Du lịch', 'Messi'})
        self.user_id = 2
        self.save(['Giáo dục'])
        self.user_id = 1
        self.save(['Messi'])
        self.assertEqual([p['topic'] for p in self.client.get('/preferences').json()['preferences']], ['Messi'])
        self.user_id = 2
        self.assertEqual([p['topic'] for p in self.client.get('/preferences').json()['preferences']], ['Giáo dục'])

    def test_main_topic_recommendations_follow_saved_user_and_keep_history(self):
        self.add_article(1, 'Thể thao')
        self.add_article(2, 'Du lịch')
        self.add_article(3, 'Thời sự')
        self.save(['Thể thao'])
        self.assertEqual(self.recommendations(), ['https://news.example/1'])
        self.user_id = 2
        self.save(['Du lịch'])
        self.assertEqual(self.recommendations(), ['https://news.example/2'])
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT user_id,article_id FROM recommendation_history ORDER BY user_id')).all(), [(1, 1), (2, 2)])

    def test_keyword_does_not_recommend_unrelated_low_score_story(self):
        self.add_article(1, 'Thể thao', content='Messi scored a goal', vector=[1.0, 0.0])
        self.add_article(2, 'Du lịch')
        self.save(['Messi'])
        self.assertEqual(self.recommendations(), ['https://news.example/1'])

    def test_new_user_without_preferences_has_no_personalized_results(self):
        self.add_article(1, 'Thể thao')
        self.assertEqual(self.recommendations(), [])

    def test_all_fourteen_summaries_use_only_selected_category_even_with_low_similarity(self):
        for article_id, topic in enumerate(MAIN_TOPICS, 1):
            self.add_article(article_id, topic)
        with patch.object(summary, 'summarize_articles', return_value='Test summary') as generate:
            for article_id, topic in enumerate(MAIN_TOPICS, 1):
                with self.subTest(topic=topic):
                    response = self.client.post('/summary', json={**self.window, 'topic': topic})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['sources'][0]['url'], f'https://news.example/{article_id}')
                    sources = generate.call_args.kwargs['articles']
                    self.assertTrue(all(row['category'] == topic for row in sources))
                    self.assertEqual(len(sources), 1)

    def test_missing_category_and_irrelevant_keyword_do_not_call_gemini(self):
        self.add_article(1, 'Thể thao')
        with patch.object(summary, 'summarize_articles') as generate:
            for topic in ('Xe', 'quantum chips'):
                response = self.client.post('/summary', json={**self.window, 'topic': topic})
                self.assertEqual(response.status_code, 404, response.text)
            generate.assert_not_called()

    def test_main_topic_normalization_and_url_restriction(self):
        self.add_article(1, 'Thể thao')
        self.add_article(2, 'Du lịch')
        rows = hybrid_search.search_hybrid('  thể thao  ', date(2026, 10, 1), date(2026, 10, 27))
        self.assertEqual([r['url'] for r in rows], ['https://news.example/1'])
        rows = hybrid_search.search_hybrid('Messi', date(2026, 10, 1), date(2026, 10, 27), article_urls={'https://news.example/2'})
        self.assertEqual([r['url'] for r in rows], ['https://news.example/2'])

    def test_endpoints_require_login(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/preferences').status_code, 401)
        self.assertEqual(self.client.put('/preferences', json={'topics': ['Messi']}).status_code, 401)
        self.assertEqual(self.client.post('/recommend', json=self.window).status_code, 401)
        self.assertEqual(self.client.post('/summary', json={**self.window, 'topic': 'Xe'}).status_code, 401)


if __name__ == '__main__':
    unittest.main()
