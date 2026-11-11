import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

FILE = Path(__file__).with_name('tuoitre_crawler.py')
spec = importlib.util.spec_from_file_location('tuoitre_test_target', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
URL = 'https://tuoitre.vn/bai-viet-thu-nghiem-100261108123456789.htm'
HTML = '''<html><head>
<meta property="article:section" content="Nhịp sống số">
<meta property="article:published_time" content="2026-11-08T08:20:00Z">
<meta property="og:image" content="https://cdn2.tuoitre.vn/cover.jpg">
</head><body><h1 class="detail-title">Tiêu đề thử</h1><h2 class="detail-sapo">Mô tả thử</h2>
<div class="detail-content"><p>Đoạn đầu.</p>
<figure><img data-original="https://cdn2.tuoitre.vn/photo.jpg" src="/placeholder.gif" onerror="alert(1)">
<figcaption>Chú thích ảnh</figcaption></figure><p>Đoạn sau.</p>
<script>bad()</script><iframe src="https://example.com"></iframe>
<div type="RelatedNewsBox"><p>Bài liên quan</p></div>
<div class="readmore-body-box"><p>Đọc thêm</p></div>
<a href="javascript:bad()" onclick="bad()">Liên kết</a>
</div></body></html>'''


class CrawlerTests(unittest.TestCase):
    def test_rss_date_formats(self):
        self.assertEqual(m.parse_published_at('11/8/2026 4:03:00\u202fPM'), datetime(2026, 11, 8, 16, 3))
        self.assertEqual(m.parse_published_at('Sun, 08 Nov 2026 16:03:00 +0700'), datetime(2026, 11, 8, 16, 3))
        self.assertEqual(m.parse_published_at('2026-11-08T09:03:00Z'), datetime(2026, 11, 8, 16, 3))
        self.assertIsNone(m.parse_published_at('not a date'))

    def test_canonical_domain_and_query(self):
        self.assertEqual(m.canonical_article_url(URL+'?utm_source=test#x'), URL)
        for url in ['https://evil.example/a-100261108123456789.htm',
                    'https://tuoitre.vn.evil.example/a-100261108123456789.htm',
                    'https://tuoitre.vn/thoi-su.htm', 'javascript:bad()',
                    'https://u:p@tuoitre.vn/a-100261108123456789.htm']:
            self.assertIsNone(m.canonical_article_url(url))

    def test_feed_deduplicates_and_rejects_foreign_links(self):
        xml = f'<rss><channel><item><link>{URL}</link><pubDate>11/8/2026 4:03:00 PM</pubDate></item><item><link>{URL}?utm_source=x</link></item><item><link>https://evil.example/a.htm</link></item></channel></rss>'
        response = SimpleNamespace(content=xml.encode(), raise_for_status=lambda: None)
        with patch.object(m.requests, 'get', return_value=response):
            entries = m.get_feed_articles('https://tuoitre.vn/home.rss')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['published_at'], datetime(2026, 11, 8, 16, 3))

    def test_metadata_and_topic_mapping(self):
        a = m.parse_article(HTML, URL, 'Thời sự')
        self.assertEqual(a['title'], 'Tiêu đề thử')
        self.assertEqual(a['main_category'], 'Công nghệ')
        self.assertEqual(a['published_at'], datetime(2026, 11, 8, 15, 20))
        self.assertEqual(a['image_url'], 'https://cdn2.tuoitre.vn/cover.jpg')

    def test_html_response_is_not_treated_as_empty_feed(self):
        response = SimpleNamespace(content=b'<html>error page</html>', raise_for_status=lambda: None)
        with patch.object(m.requests, 'get', return_value=response), self.assertRaises(ValueError):
            m.get_feed_articles('https://tuoitre.vn/home.rss')

    def test_body_sanitization_and_order(self):
        a = m.parse_article(HTML, URL)
        for bad in ['<script', '<iframe', 'onerror', 'onclick', 'javascript:', 'Bài liên quan', 'Đọc thêm']:
            self.assertNotIn(bad, a['content_html'])
        html = a['content_html']
        self.assertLess(html.index('Đoạn đầu'), html.index('photo.jpg'))
        self.assertLess(html.index('photo.jpg'), html.index('Đoạn sau'))
        self.assertIn('Chú thích ảnh', html)

    def test_jsonld_graph_and_image_fallback(self):
        html = '''<script type="application/ld+json">{"@graph":[{"@type":"Organization"},{"@type":["Article"],"headline":"Tên bài","datePublished":"2026-11-08T10:00:00+07:00","articleSection":"Nhà đất"}]}</script><div class="detail-content"><p>Nội dung</p><img src="/image.jpg"></div>'''
        a = m.parse_article(html, URL)
        self.assertEqual(a['title'], 'Tên bài')
        self.assertEqual(a['main_category'], 'Bất động sản')
        self.assertEqual(a['image_url'], 'https://tuoitre.vn/image.jpg')

    def test_missing_body_is_not_invented(self):
        self.assertEqual(m.parse_article('<h1>Tên bài</h1>', URL, 'Thời sự')['content'], '')

    def test_invalid_settings(self):
        for kwargs in [{'days':0}, {'max_articles':0}, {'limit_per_category':0}, {'categories':['Sai']}]:
            with self.assertRaises(ValueError):
                m.main(dry_run=True, **kwargs)

    def test_write_dedup_and_reject_invalid_articles(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        with engine.begin() as c:
            c.execute(text('CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, description TEXT, content TEXT, content_html TEXT, category TEXT, main_category TEXT, url TEXT UNIQUE, image_url TEXT, published_at DATETIME)'))
        db = ModuleType('src.db.db'); db.engine = engine
        now = datetime.now(m.VIETNAM_TZ).replace(tzinfo=None) - timedelta(seconds=10)
        valid = dict(m.parse_article(HTML, URL), published_at=now)
        entries = [{'url':URL,'published_at':now}, {'url':URL,'published_at':now}]
        with patch.dict(sys.modules, {'src.db.db':db}), patch.object(m, 'get_feed_articles', return_value=entries), patch.object(m, 'get_article', return_value=valid) as fetch, patch.object(m.time, 'sleep'), redirect_stdout(io.StringIO()):
            self.assertEqual(len(m.main(categories=['Thời sự'])), 1)
            self.assertEqual(len(m.main(categories=['Thời sự'])), 0)
            self.assertEqual(fetch.call_count, 1)
        bad = dict(valid, content='')
        with patch.dict(sys.modules, {'src.db.db':db}), patch.object(m, 'get_feed_articles', return_value=[{'url':URL+'2','published_at':now}]), patch.object(m, 'get_article', return_value=bad), patch.object(m.time, 'sleep'), redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(categories=['Thời sự']), [])
        with engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT COUNT(*) FROM articles')).scalar(), 1)

    def test_dry_run_cap_and_source_failure_isolation(self):
        now = datetime.now(m.VIETNAM_TZ).replace(tzinfo=None) - timedelta(seconds=10)
        a = dict(m.parse_article(HTML, URL), published_at=now)
        with patch.object(m, 'get_feed_articles', side_effect=[RuntimeError(), [{'url':URL,'published_at':now}]]), patch.object(m, 'get_article', return_value=a), patch.object(m.time, 'sleep'), redirect_stdout(io.StringIO()):
            self.assertEqual(len(m.main(categories=['Thời sự','Công nghệ'], dry_run=True, max_articles=1)), 1)

    def test_update_pipeline_includes_tuoitre_and_preserves_processing(self):
        names = ['src.crawler.vnexpress_crawler','src.crawler.dantri_crawler','src.crawler.tuoitre_crawler', 'src.crawler.vietnamnet_crawler','src.embedding.generate_embeddings','src.notifications.service']
        from unittest.mock import Mock
        modules = {}
        events = []
        for name in names:
            mod = ModuleType(name)
            if name.endswith('service'):
                mod.notify_new_articles = Mock(side_effect=lambda articles:events.append(('notify',articles)))
            elif name.endswith('generate_embeddings'):
                mod.main = Mock(side_effect=lambda:events.append(('embed',None)))
            else:
                mod.main = Mock(return_value=[{'source':name}])
            modules[name]=mod
        settings = ModuleType('src.db.admin_store')
        settings.init_admin_tables = Mock()
        settings.get_sources = Mock(return_value=[{'code':code,'name':code,'enabled':True} for code in ['vnexpress','dantri','tuoitre','vietnamnet']])
        settings.source_started = Mock()
        settings.source_finished = Mock()
        modules['src.db.admin_store'] = settings
        with patch.dict(sys.modules, modules), redirect_stdout(io.StringIO()):
            spec = importlib.util.spec_from_file_location('pipeline_target', FILE.parents[1] / 'update_news.py')
            pipeline = importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
            pipeline.main()
        modules[names[2]].main.assert_called_once_with(days=2,limit_per_category=5)
        self.assertEqual([event[0] for event in events], ['embed','notify'])
        self.assertEqual(len(events[1][1]),4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
