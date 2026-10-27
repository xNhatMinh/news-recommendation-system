import os
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from src.news_topics import MAIN_TOPICS, get_main_category

with patch.dict(os.environ, {
    "MYSQL_USER": "test", "MYSQL_PASSWORD": "test", "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306", "MYSQL_DATABASE": "test",
}):
    from src.crawler import backfill_main_category as backfill
    from src.crawler import vnexpress_crawler as crawler


def page(*paths):
    return BeautifulSoup('<ul class="breadcrumb">' + ''.join(
        f'<li><a href="{path}">Tin tức</a></li>' for path in paths
    ) + '</ul><h1 class="title-detail">Bài thử</h1>', 'html.parser')


class MainTopicsTests(unittest.TestCase):
    def test_fourteen_main_topics(self):
        self.assertEqual(len(MAIN_TOPICS), 14)
        self.assertEqual(len(set(MAIN_TOPICS)), 14)

    def test_parent_uses_path_even_with_shared_child_names(self):
        for path, expected in (
            ('/suc-khoe/vaccine/tin-tuc', 'Sức khỏe'),
            ('/giao-duc/tin-tuc', 'Giáo dục'),
            ('/the-gioi/bac-my', 'Thế giới'),
            ('/doi-song/bai-hoc-song', 'Đời sống'),
            ('/oto-xe-may/thi-truong', 'Xe'),
            ('/bat-dong-san/chinh-sach', 'Bất động sản'),
            ('/thoi-su/mekong/kham-pha', 'Thời sự'),
            ('https://vnexpress.net/phap-luat', 'Pháp luật'),
        ):
            with self.subTest(path=path):
                self.assertEqual(get_main_category(page(path)), expected)

    def test_science_and_technology_follow_child_path(self):
        for section, expected in (
            ('ai', 'Công nghệ'), ('thiet-bi', 'Công nghệ'),
            ('chuyen-doi-so', 'Công nghệ'), ('vu-tru', 'Khoa học'),
            ('the-gioi-tu-nhien', 'Khoa học'),
        ):
            with self.subTest(section=section):
                soup = page('/khoa-hoc-cong-nghe', '/khoa-hoc-cong-nghe/' + section)
                self.assertEqual(get_main_category(soup), expected)
        self.assertEqual(get_main_category(page('/so-hoa/nhip-song-so')), 'Công nghệ')

    def test_unknown_breadcrumb_does_not_guess_topic(self):
        self.assertIsNone(get_main_category(page('/unknown')))
        self.assertIsNone(get_main_category(BeautifulSoup('<p>AI</p>', 'html.parser')))

    def test_crawler_saves_both_parent_and_child(self):
        with patch.object(crawler, 'get_soup', return_value=page('/the-gioi', '/the-gioi/bac-my')):
            article = crawler.get_article('https://news.example/test.html')
        self.assertEqual(article['main_category'], 'Thế giới')
        self.assertEqual(article['category'], 'Tin tức')

    def test_backfill_adds_column_keeps_child_and_resumes(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT, category TEXT)'))
            connection.execute(text("INSERT INTO articles VALUES (1, 'one', 'Bắc Mỹ'), (2, 'two', 'Thời sự')"))
        with patch.object(backfill, 'engine', engine), patch.object(backfill, 'get_soup', return_value=page('/the-gioi/bac-my')) as fetch, patch.object(backfill.time, 'sleep'):
            self.assertEqual(backfill.backfill_main_category(1), {'updated': 2, 'skipped': 0, 'failed': 0})
            self.assertEqual(backfill.backfill_main_category(1), {'updated': 0, 'skipped': 0, 'failed': 0})
            self.assertEqual(fetch.call_count, 1)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT category, main_category FROM articles WHERE id = 1')).one(), ('Bắc Mỹ', 'Thế giới'))

    def test_existing_parent_is_not_overwritten(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY, main_category TEXT)'))
            connection.execute(text("INSERT INTO articles VALUES (1, 'Giáo dục')"))
        with patch.object(backfill, 'engine', engine), patch.object(backfill, 'get_soup', return_value=page('/the-gioi/bac-my')), patch.object(backfill.time, 'sleep'):
            status, _ = backfill.update_main_category({'id': 1, 'url': 'one'})
        self.assertEqual(status, 'skipped')
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT main_category FROM articles')).scalar(), 'Giáo dục')


if __name__ == '__main__':
    unittest.main()
