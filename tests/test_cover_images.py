import os
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

with patch.dict(os.environ, {
    "MYSQL_USER": "test", "MYSQL_PASSWORD": "test", "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306", "MYSQL_DATABASE": "test",
}):
    from src.crawler import backfill_cover_images as backfill
    from src.crawler.vnexpress_crawler import get_cover_image


class CoverImageTests(unittest.TestCase):
    def test_meta_cover_is_preferred_over_content_image(self):
        soup = BeautifulSoup('<meta property="og:image" content="/cover.jpg"><article class="fck_detail"><img src="/body.jpg"></article>', 'html.parser')
        self.assertEqual(get_cover_image(soup, 'https://news.example/post'), 'https://news.example/cover.jpg')

    def test_blank_or_placeholder_meta_falls_back_to_real_lazy_image(self):
        soup = BeautifulSoup('<meta property="og:image" content=""><img src="data:image/gif;base64,test"><img data-src="//images.example/real.jpg" src="data:image/gif;base64,test">', 'html.parser')
        self.assertEqual(get_cover_image(soup, 'https://news.example/post'), 'https://images.example/real.jpg')
        self.assertIsNone(get_cover_image(BeautifulSoup('<img src="javascript:test">', 'html.parser'), 'https://news.example/post'))

    def test_twitter_cover_and_no_image_page(self):
        soup = BeautifulSoup('<meta name="twitter:image" content="https://images.example/cover.jpg">', 'html.parser')
        self.assertEqual(get_cover_image(soup, 'https://news.example/post'), 'https://images.example/cover.jpg')
        self.assertIsNone(get_cover_image(BeautifulSoup('<p>Text only</p>', 'html.parser'), 'https://news.example/post'))

    def test_backfill_keeps_existing_covers_and_body_html_and_can_resume(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.addCleanup(engine.dispose)
        html = '<figure><img src="https://images.example/body.jpg"></figure>'
        with engine.begin() as c:
            c.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY,url TEXT,image_url TEXT,content_html TEXT)'))
            c.execute(text('INSERT INTO articles VALUES (:id,:url,:cover,:html)'), [
                {'id': 1, 'url': 'https://news.example/one', 'cover': None, 'html': html},
                {'id': 2, 'url': 'https://news.example/two', 'cover': 'https://images.example/keep.jpg', 'html': html},
                {'id': 3, 'url': 'https://news.example/three', 'cover': '', 'html': ''},
            ])
        source = BeautifulSoup('<meta property="og:image" content="https://images.example/source.jpg">', 'html.parser')
        with patch.object(backfill, 'engine', engine), patch.object(backfill, 'get_soup', return_value=source) as fetch, patch.object(backfill.time, 'sleep'):
            self.assertEqual(backfill.backfill_cover_images(), {'updated': 2, 'no_image': 0, 'failed': 0})
            self.assertEqual(backfill.backfill_cover_images(), {'updated': 0, 'no_image': 0, 'failed': 0})
            self.assertEqual(fetch.call_count, 1)
        with engine.connect() as c:
            rows = c.execute(text('SELECT image_url,content_html FROM articles ORDER BY id')).all()
        self.assertEqual(rows[0], ('https://images.example/body.jpg', html))
        self.assertEqual(rows[1], ('https://images.example/keep.jpg', html))
        self.assertEqual(rows[2][0], 'https://images.example/source.jpg')


if __name__ == '__main__':
    unittest.main()
