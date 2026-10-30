import contextlib
import io
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

with patch.dict(os.environ, {
    "MYSQL_USER": "test", "MYSQL_PASSWORD": "test", "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306", "MYSQL_DATABASE": "test",
}):
    from src.crawler import vnexpress_crawler as crawler


class CrawlerLinkTests(unittest.TestCase):
    def test_collects_h3_and_h4_titles_without_ads_or_duplicate_urls(self):
        html = """
            <article class="item-news"><h3 class="title-news"><a href="https://vnexpress.net/first.html">First</a></h3></article>
            <article class="item-news"><h4 class="title-news"><a href="https://vnexpress.net/second.html">Second</a></h4></article>
            <article class="item-news"><h4 class="title-news"><a href="https://vnexpress.net/first.html">Duplicate</a></h4></article>
            <article class="item-news"><a href="https://vnexpress.net/ad.html">Ad</a></article>
        """
        with patch.object(crawler, 'get_soup', return_value=BeautifulSoup(html, 'html.parser')), patch.object(crawler.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            urls = crawler.get_article_urls('https://vnexpress.net/khoa-hoc-cong-nghe', datetime(2026, 10, 1), max_pages=1)
        self.assertEqual(urls, ['https://vnexpress.net/first.html', 'https://vnexpress.net/second.html'])


    def test_topic_crawl_keeps_valid_articles_and_skips_existing_urls(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        with engine.begin() as c:
            c.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY,title TEXT,description TEXT,content TEXT,content_html TEXT,category TEXT,main_category TEXT,url TEXT UNIQUE,image_url TEXT,published_at TIMESTAMP)'))
            c.execute(text("INSERT INTO articles (url) VALUES ('https://news.example/existing')"))
        now = datetime.now()
        template = {
            'title': 'Valid article', 'description': '', 'content': 'Body',
            'content_html': '<p>Body</p>', 'category': 'Tin tức',
            'main_category': 'Giáo dục', 'image_url': 'https://images.example/cover.jpg',
            'published_at': now - timedelta(days=1),
        }
        stories = {}
        for key, changes in (
            ('new', {}), ('existing', {}),
            ('old', {'published_at': now - timedelta(days=40)}),
            ('future', {'published_at': now + timedelta(days=1)}),
            ('wrong-topic', {'main_category': 'Du lịch'}),
            ('empty', {'content': ''}), ('no-date', {'published_at': None}),
        ):
            url = 'https://news.example/' + key
            stories[url] = {**template, **changes, 'url': url}
        with patch.object(crawler, 'engine', engine), patch.object(crawler, 'get_article_urls', return_value=list(stories)), patch.object(crawler, 'get_article', side_effect=lambda url: stories[url]), patch.object(crawler.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            inserted = crawler.main(categories=['Giáo dục'], days=30, max_pages=1)
            again = crawler.main(categories=['Giáo dục'], days=30, max_pages=1)
        self.assertEqual([a['url'] for a in inserted], ['https://news.example/new'])
        self.assertEqual(again, [])
        with engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT COUNT(*) FROM articles')).scalar(), 2)
            self.assertEqual(c.execute(text("SELECT main_category,content_html FROM articles WHERE url='https://news.example/new'")).one(), ('Giáo dục', '<p>Body</p>'))


if __name__ == '__main__':
    unittest.main()
