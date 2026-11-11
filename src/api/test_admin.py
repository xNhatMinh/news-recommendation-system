import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['JWT_SECRET_KEY']='isolated-admin-test-secret-long-enough-123456'
os.environ['N8N_KEY']='isolated-internal-key'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

ROOT=Path(__file__).resolve().parents[2]
engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
db=types.ModuleType('src.db.db');db.engine=engine;sys.modules['src.db.db']=db

def load(name,rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

security=load('src.api.security','src/api/security.py')
store=load('src.db.admin_store','src/db/admin_store.py')
fake_update=types.ModuleType('src.update_news')
fake_update.main=Mock(return_value={'status':'finished','new_articles':2,'sources':[]})
sys.modules['src.update_news']=fake_update
automation=load('src.api.routes.automation','src/api/routes/automation.py')
admin=load('src.api.routes.admin','src/api/routes/admin.py')
articles=load('public_articles','src/api/routes/articles.py')
# Minimal identity stub for the existing personal article lists.
auth=types.ModuleType('src.api.routes.auth');auth.get_me=lambda:{'user_id':1,'email':'test@example.com'}
sys.modules['src.api.routes.auth']=auth
bookmarks=load('public_bookmarks','src/api/routes/bookmarks.py')
notification_store=load('src.notifications.store','src/notifications/store.py')
notifications=load('public_notifications','src/api/routes/notifications.py')
explainer=types.ModuleType('src.summarization.term_explainer');explainer.explain_term=Mock(return_value='Lời giải thích')
sys.modules['src.summarization.term_explainer']=explainer
terms=load('public_terms','src/api/routes/terms.py')
app=FastAPI()
for module in [admin,automation,articles,bookmarks,notifications,terms]:app.include_router(module.router)
client=TestClient(app)
PASSWORD='Test-admin-password-123'
HASH=security.hash_admin_password(PASSWORD)

class AdminTests(unittest.TestCase):
    def setUp(self):
        os.environ['ADMIN_USERNAME']='admin';os.environ['ADMIN_PASSWORD_HASH']=HASH
        admin.login_attempts.clear()
        automation.job.clear();automation.job.update(status='idle',message='Chưa chạy')
        fake_update.main.reset_mock()
        for table in ['user_notifications','user_bookmarks','user_devices','users','articles','hidden_articles','news_sources']:
            with engine.begin() as c:c.execute(text('DROP TABLE IF EXISTS '+table))
        with engine.begin() as c:
            c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,email TEXT,created_at DATETIME)'))
            c.execute(text("INSERT INTO users VALUES(1,'test_user','user@example.com','2026-11-08')"))
            c.execute(text('CREATE TABLE user_devices(id INTEGER PRIMARY KEY,user_id INTEGER,fcm_token TEXT)'))
            c.execute(text('CREATE TABLE articles(id INTEGER PRIMARY KEY, title TEXT, description TEXT, content TEXT, content_html TEXT, category TEXT, main_category TEXT, url TEXT, image_url TEXT, published_at DATETIME)'))
            c.execute(text('CREATE TABLE user_bookmarks(id INTEGER PRIMARY KEY,user_id INTEGER,article_id INTEGER,created_at DATETIME)'))
            c.execute(text('CREATE TABLE user_notifications(id INTEGER PRIMARY KEY,user_id INTEGER,article_id INTEGER,topic TEXT,is_read INTEGER,created_at DATETIME)'))
            c.execute(text("INSERT INTO articles VALUES (1,'Tin vàng','','Nội dung vàng','<p>Nội dung vàng</p>','Kinh doanh','Kinh doanh','https://vnexpress.net/a',NULL,'2026-11-08 10:00:00'),(2,'Tin mới','','Nội dung','<p>Nội dung</p>','Thời sự','Thời sự','https://tuoitre.vn/a',NULL,'2026-11-08 11:00:00')"))
            c.execute(text("INSERT INTO user_bookmarks VALUES(1,1,1,'2026-11-08')"))
            c.execute(text("INSERT INTO user_notifications VALUES(1,1,1,'vàng',0,'2026-11-08')"))
        store.init_admin_tables()
        self.headers={'Authorization':'Bearer '+security.create_access_token('admin:admin',role='admin')}

    def test_admin_page_is_public_but_contains_no_credentials(self):
        r=client.get('/admin');self.assertEqual(r.status_code,200);self.assertNotIn(PASSWORD,r.text)

    def test_login_and_jwt_roles(self):
        r=client.post('/admin/login',json={'username':'admin','password':PASSWORD})
        self.assertEqual(r.status_code,200)
        payload=security.decode_access_token(r.json()['access_token'])
        self.assertEqual(payload['role'],'admin');self.assertEqual(payload['sub'],'admin:admin')

    def test_all_admin_operations_require_auth(self):
        for method,url,body in [('get','/admin/overview',None),('get','/admin/articles',None),('get','/admin/articles/1',None),('get','/admin/update-news/status',None),('patch','/admin/sources/vnexpress',{'enabled':False}),('patch','/admin/articles/1',{'hidden':True}),('post','/admin/update-news',{})]:
            r=getattr(client,method)(url,**({'json':body} if body is not None else {}));self.assertEqual(r.status_code,401,url)

    def test_regular_user_token_cannot_access_admin(self):
        headers={'Authorization':'Bearer '+security.create_access_token(1)}
        self.assertEqual(client.get('/admin/overview',headers=headers).status_code,403)
        self.assertEqual(client.patch('/admin/articles/1',headers=headers,json={'hidden':True}).status_code,403)

    def test_wrong_password_and_rate_limit(self):
        for _ in range(5):self.assertEqual(client.post('/admin/login',json={'username':'admin','password':'bad'}).status_code,401)
        self.assertEqual(client.post('/admin/login',json={'username':'admin','password':PASSWORD}).status_code,429)

    def test_missing_admin_configuration(self):
        os.environ.pop('ADMIN_PASSWORD_HASH')
        self.assertEqual(client.post('/admin/login',json={'username':'admin','password':PASSWORD}).status_code,503)

    def test_password_hash(self):
        self.assertTrue(security.verify_admin_password(PASSWORD,HASH))
        self.assertFalse(security.verify_admin_password('wrong',HASH))
        self.assertFalse(security.verify_admin_password(PASSWORD,'invalid'))

    def test_overview_and_source_toggle(self):
        result=client.get('/admin/overview',headers=self.headers).json()
        self.assertEqual(result['total_articles'],2);self.assertEqual(len(result['sources']),4)
        self.assertEqual(client.patch('/admin/sources/tuoitre',headers=self.headers,json={'enabled':False}).status_code,200)
        self.assertFalse(next(s for s in store.get_sources() if s['code']=='tuoitre')['enabled'])
        self.assertEqual(client.patch('/admin/sources/evil',headers=self.headers,json={'enabled':True}).status_code,404)
        self.assertEqual(client.patch('/admin/sources/tuoitre',headers=self.headers,json={'enabled':'false'}).status_code,422)

    def test_selected_source_update_reuses_shared_job(self):
        r=client.post('/admin/update-news',headers=self.headers,json={'sources':['tuoitre']})
        self.assertEqual(r.status_code,202);self.assertEqual(r.json()['status'],'accepted')
        fake_update.main.assert_called_once_with(sources=['tuoitre'])
        self.assertEqual(client.get('/admin/update-news/status',headers=self.headers).json()['status'],'finished')

    def test_disabled_source_rejected_and_busy_job_skipped(self):
        store.set_source_enabled('tuoitre',False)
        self.assertEqual(client.post('/admin/update-news',headers=self.headers,json={'sources':['tuoitre']}).status_code,400)
        automation.job['status']='running'
        r=client.post('/admin/update-news',headers=self.headers,json={})
        self.assertEqual(r.json()['status'],'skipped');fake_update.main.assert_not_called()

    def test_n8n_key_still_required_and_shares_update(self):
        self.assertEqual(client.post('/internal/update-news').status_code,401)
        self.assertEqual(client.post('/internal/update-news',headers={'X-Update-Key':'isolated-internal-key'}).status_code,202)
        fake_update.main.assert_called_once_with(sources=None)

    def test_background_error_changes_job_status(self):
        with patch.object(automation,'run_update',side_effect=RuntimeError()):
            client.post('/admin/update-news',headers=self.headers,json={})
        self.assertEqual(automation.job['status'],'failed')

    def test_hide_and_restore_updates_all_read_lists(self):
        self.assertEqual(client.patch('/admin/articles/1',headers=self.headers,json={'hidden':True}).status_code,200)
        latest=client.get('/articles/latest').json()['results']
        self.assertEqual(len(latest),1);self.assertEqual(latest[0]['url'],'https://tuoitre.vn/a')
        self.assertEqual(client.get('/articles/detail',params={'url':'https://vnexpress.net/a'}).status_code,404)
        self.assertEqual(client.post('/articles/explain-term',json={'url':'https://vnexpress.net/a','term':'vàng'}).status_code,404)
        self.assertEqual(client.get('/bookmarks').json()['results'],[])
        self.assertEqual(client.get('/notifications').json()['results'],[])
        self.assertEqual(client.get('/notifications/unread-count').json()['unread_count'],0)
        self.assertFalse(notification_store.save_notification(1,'https://vnexpress.net/a','vàng'))
        self.assertEqual(client.get('/admin/articles/1',headers=self.headers).status_code,200)
        client.patch('/admin/articles/1',headers=self.headers,json={'hidden':False})
        self.assertEqual(len(client.get('/articles/latest').json()['results']),2)
        self.assertEqual(client.get('/notifications/unread-count').json()['unread_count'],1)

    def test_missing_article_and_idempotent_toggle(self):
        self.assertEqual(client.patch('/admin/articles/999',headers=self.headers,json={'hidden':True}).status_code,404)
        for _ in range(2):self.assertEqual(client.patch('/admin/articles/1',headers=self.headers,json={'hidden':True}).status_code,200)
        with engine.connect() as c:self.assertEqual(c.execute(text('SELECT COUNT(*) FROM hidden_articles')).scalar(),1)

    def test_article_search_filters_pagination_and_injection(self):
        r=client.get('/admin/articles',headers=self.headers,params={'limit':1}).json()
        self.assertEqual(len(r['results']),1);self.assertTrue(r['has_more'])
        r=client.get('/admin/articles',headers=self.headers,params={'q':'vàng','source':'vnexpress'}).json()
        self.assertEqual(len(r['results']),1)
        self.assertEqual(client.get('/admin/articles',headers=self.headers,params={'q':"'; DROP TABLE articles;--"}).json()['results'],[])
        self.assertEqual(client.get('/admin/articles',headers=self.headers,params={'visibility':'invalid'}).status_code,422)
        self.assertEqual(client.get('/admin/articles',headers=self.headers,params={'source':'invalid'}).status_code,422)
        self.assertEqual(client.get('/admin/articles',headers=self.headers,params={'limit':0}).status_code,422)

    def test_hidden_article_excluded_from_semantic_search(self):
        with engine.begin() as c:
            c.execute(text('CREATE TABLE IF NOT EXISTS article_embeddings(article_id INTEGER,embedding TEXT)'))
            c.execute(text('DELETE FROM article_embeddings'))
            c.execute(text("INSERT INTO article_embeddings VALUES(1,'[1,0]'),(2,'[1,0]')"))
        store.set_article_hidden(1,True)
        model=types.ModuleType('src.embedding.model');model.model=types.SimpleNamespace(encode=lambda values:[[1,0]])
        pairwise=types.ModuleType('sklearn.metrics.pairwise');pairwise.cosine_similarity=lambda a,b:[[1.0]]
        with patch.dict(sys.modules,{'src.embedding.model':model,'sklearn.metrics.pairwise':pairwise}):
            hybrid=load('hybrid_test_target','src/embedding/hybrid_search.py')
            from datetime import date
            result=hybrid.search_hybrid('tin',date(2026,11,1),date(2026,11,30))
        self.assertEqual([a['url'] for a in result],['https://tuoitre.vn/a'])


if __name__=='__main__':unittest.main(verbosity=2)
