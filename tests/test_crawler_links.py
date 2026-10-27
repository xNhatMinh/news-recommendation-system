import contextlib
import io
import os
import unittest
from datetime import datetime
from unittest.mock import patch
from bs4 import BeautifulSoup

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


if __name__ == '__main__':
    unittest.main()
