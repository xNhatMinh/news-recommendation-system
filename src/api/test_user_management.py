"""User management integration tests with SQLite and mocked Firebase identity."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['JWT_SECRET_KEY'] = 'user-management-isolated-test-secret-1234567890'
os.environ['N8N_KEY'] = 'test-update-key'
os.environ['ADMIN_USERNAME'] = 'admin'

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
db = types.ModuleType('src.db.db'); db.engine = engine
sys.modules['src.db.db'] = db
firebase = types.ModuleType('src.auth.firebase_service')
firebase.authenticate = Mock(); firebase.authenticate_google = Mock(); firebase.send_password_reset_email = Mock()
sys.modules[firebase.__name__] = firebase
update = types.ModuleType('src.update_news'); update.main = Mock()
sys.modules[update.__name__] = update
config = types.ModuleType('src.notifications.firebase_config'); config.firebase_app = object()
sys.modules[config.__name__] = config
hybrid = types.ModuleType('src.embedding.hybrid_search')
hybrid.MIN_RELEVANCE_SCORE = .5; hybrid.search_hybrid = Mock()
sys.modules[hybrid.__name__] = hybrid

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

security = load('src.api.security', 'src/api/security.py')
store = load('src.db.admin_store', 'src/db/admin_store.py')
auth = load('src.api.routes.auth', 'src/api/routes/auth.py')
automation = load('src.api.routes.automation', 'src/api/routes/automation.py')
admin = load('src.api.routes.admin', 'src/api/routes/admin.py')
sender = load('src.notifications.sender', 'src/notifications/sender.py')
notification_store = load('src.notifications.store', 'src/notifications/store.py')
notification_service = load('src.notifications.service', 'src/notifications/service.py')
app = FastAPI()
for module in [auth, admin]: app.include_router(module.router)
for name in ['preferences', 'bookmarks', 'notifications', 'devices']:
    module = load('src.api.routes.' + name, 'src/api/routes/' + name + '.py')
    app.include_router(module.router)
client = TestClient(app)


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        with engine.begin() as c:
            for table in inspect(c).get_table_names():
                c.execute(text('DROP TABLE ' + table))
            c.execute(text('''CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE,
                              email TEXT UNIQUE,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,password_hash TEXT)'''))
            c.execute(text("INSERT INTO users(id,username,email) VALUES(1,'alpha','alpha@example.com'),(2,'beta','beta@example.com')"))
            c.execute(text('''CREATE TABLE user_firebase_accounts(user_id INTEGER PRIMARY KEY,firebase_uid TEXT UNIQUE,
                              created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'''))
            c.execute(text("INSERT INTO user_firebase_accounts(user_id,firebase_uid) VALUES(1,'uid-alpha'),(2,'uid-beta')"))
            c.execute(text('CREATE TABLE user_devices(id INTEGER PRIMARY KEY,user_id INTEGER,fcm_token TEXT UNIQUE)'))
            c.execute(text("INSERT INTO user_devices VALUES(1,1,'test-device')"))
            c.execute(text('CREATE TABLE user_preferences(id INTEGER PRIMARY KEY,user_id INTEGER,topic TEXT,weight FLOAT)'))
            c.execute(text("INSERT INTO user_preferences VALUES(1,1,'Thể thao',1),(2,2,'Kinh doanh',1)"))
            c.execute(text('CREATE TABLE user_bookmarks(id INTEGER PRIMARY KEY,user_id INTEGER,article_id INTEGER,created_at DATETIME)'))
            c.execute(text("INSERT INTO user_bookmarks VALUES(1,1,1,'2026-11-10')"))
            c.execute(text('''CREATE TABLE user_notifications(id INTEGER PRIMARY KEY,user_id INTEGER,article_id INTEGER,
                              topic TEXT,is_read BOOLEAN,created_at DATETIME,UNIQUE(user_id,article_id))'''))
            c.execute(text("INSERT INTO user_notifications VALUES(1,1,1,'Thể thao',0,'2026-11-10')"))
            c.execute(text('CREATE TABLE articles(id INTEGER PRIMARY KEY,title TEXT,description TEXT,url TEXT UNIQUE)'))
            c.execute(text("INSERT INTO articles VALUES(1,'Bài thử','','https://example.com/a'),(2,'Bài mới','','https://example.com/b')"))
        store.init_admin_tables()
        identity = {'uid': 'uid-alpha', 'email': 'alpha@example.com'}
        firebase.authenticate.reset_mock(); firebase.authenticate.return_value = identity
        firebase.authenticate_google.reset_mock(); firebase.authenticate_google.return_value = identity
        self.admin_headers = {'Authorization': 'Bearer ' + security.create_access_token('admin:admin', role='admin')}
        self.user_headers = {'Authorization': 'Bearer ' + security.create_access_token(1, token_version=0)}

    def change(self, active, user_id=1):
        return client.patch(f'/admin/users/{user_id}', headers=self.admin_headers, json={'is_active': active})

    def login(self):
        return client.post('/auth/login', json={'email': 'alpha@example.com', 'password': 'test-password-123'})

    def row(self, user_id=1):
        with engine.connect() as c:
            return c.execute(text('SELECT * FROM users WHERE id=:id'), {'id': user_id}).mappings().one()

    def test_migration_preserves_accounts_and_adds_defaults(self):
        self.assertTrue(self.row()['is_active']); self.assertEqual(self.row()['token_version'], 0)
        self.assertEqual(self.row()['email'], 'alpha@example.com')

    def test_repeated_initialization_preserves_locked_status_and_version(self):
        self.change(False); store.init_admin_tables(); store.init_admin_tables()
        self.assertFalse(self.row()['is_active']); self.assertEqual(self.row()['token_version'], 1)

    def test_partial_migration_preserves_existing_status(self):
        other = create_engine('sqlite://')
        try:
            with other.begin() as c:
                c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY,is_active BOOLEAN NOT NULL DEFAULT TRUE)'))
                c.execute(text('INSERT INTO users VALUES(1,0)'))
            with patch.object(store, 'engine', other): store.init_user_columns()
            with other.connect() as c:
                row = c.execute(text('SELECT is_active,token_version FROM users')).one()
            self.assertEqual(tuple(row), (0, 0))
        finally: other.dispose()

    def test_management_routes_require_authentication(self):
        self.assertEqual(client.get('/admin/users').status_code, 401)
        self.assertEqual(client.patch('/admin/users/1', json={'is_active': False}).status_code, 401)

    def test_regular_user_cannot_manage_accounts(self):
        self.assertEqual(client.get('/admin/users', headers=self.user_headers).status_code, 403)
        self.assertEqual(client.patch('/admin/users/2', headers=self.user_headers, json={'is_active': False}).status_code, 403)
        self.assertTrue(self.row(2)['is_active'])

    def test_search_by_email_and_username_with_pagination(self):
        first = client.get('/admin/users?limit=1', headers=self.admin_headers).json()
        second = client.get('/admin/users?limit=1&offset=1', headers=self.admin_headers).json()
        self.assertTrue(first['has_more']); self.assertEqual(first['total_count'], 2)
        self.assertNotEqual(first['results'][0]['id'], second['results'][0]['id'])
        for query in ['ALPHA@EXAMPLE.COM', 'alpha']:
            result = client.get('/admin/users', params={'q': query}, headers=self.admin_headers).json()
            self.assertEqual([r['id'] for r in result['results']], [1])

    def test_status_filter_and_overview_counts(self):
        self.change(False)
        for status, expected in [('active', 2), ('locked', 1)]:
            data = client.get('/admin/users', params={'account_status': status}, headers=self.admin_headers).json()
            self.assertEqual([r['id'] for r in data['results']], [expected])
        data = client.get('/admin/overview', headers=self.admin_headers).json()
        self.assertEqual((data['total_users'], data['locked_users']), (2, 1))

    def test_empty_search_and_sql_input_are_safe(self):
        data = client.get('/admin/users', params={'q': "'; DROP TABLE users;--"}, headers=self.admin_headers).json()
        self.assertEqual(data['results'], []); self.assertEqual(data['total_count'], 0)
        self.assertEqual(self.row()['id'], 1)

    def test_validation_and_missing_account(self):
        for value in ['false', 0, None]:
            self.assertEqual(client.patch('/admin/users/1', headers=self.admin_headers, json={'is_active': value}).status_code, 422)
        for params in [{'limit': 0}, {'offset': -1}, {'account_status': 'invalid'}, {'q': 'x'*201}]:
            self.assertEqual(client.get('/admin/users', headers=self.admin_headers, params=params).status_code, 422)
        self.assertEqual(self.change(False, 999).status_code, 404)

    def test_user_list_does_not_expose_password_hash_or_token_version(self):
        data = client.get('/admin/users', headers=self.admin_headers).json()['results'][0]
        self.assertNotIn('password_hash', data); self.assertNotIn('token_version', data)
        self.assertIsInstance(data['is_active'], bool)

    def test_lock_revokes_old_tokens_on_personal_routes(self):
        self.assertEqual(client.get('/auth/me', headers=self.user_headers).status_code, 200)
        self.change(False)
        for path in ['/auth/me', '/preferences', '/bookmarks', '/notifications', '/notifications/unread-count']:
            self.assertEqual(client.get(path, headers=self.user_headers).status_code, 401, path)
        self.assertEqual(client.post('/devices', headers=self.user_headers, json={'fcm_token': 'new-device'}).status_code, 401)

    def test_password_and_google_login_reject_locked_accounts(self):
        self.change(False)
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(client.post('/auth/google', json={'id_token': 'verified-by-mock'}).status_code, 403)

    def test_unlock_requires_fresh_login_and_does_not_revive_old_tokens(self):
        self.change(False); self.change(True)
        self.assertEqual(client.get('/auth/me', headers=self.user_headers).status_code, 401)
        response = self.login(); self.assertEqual(response.status_code, 200)
        token = response.json()['access_token']; payload = security.decode_access_token(token)
        self.assertEqual(payload['ver'], 2)
        self.assertEqual(client.get('/auth/me', headers={'Authorization': 'Bearer '+token}).status_code, 200)

    def test_legacy_tokens_work_until_status_changes(self):
        headers = {'Authorization': 'Bearer '+security.create_access_token(1)}
        self.assertEqual(client.get('/auth/me', headers=headers).status_code, 200)
        self.change(False); self.change(True)
        self.assertEqual(client.get('/auth/me', headers=headers).status_code, 401)

    def test_repeating_same_status_is_idempotent(self):
        self.change(False); self.change(False)
        self.assertEqual(self.row()['token_version'], 1)
        self.change(True); self.change(True)
        self.assertEqual(self.row()['token_version'], 2)

    def test_lock_retains_personal_data_and_removes_push_registrations(self):
        self.change(False)
        with engine.connect() as c:
            for table in ['user_preferences', 'user_bookmarks', 'user_notifications', 'user_firebase_accounts']:
                self.assertGreater(c.execute(text('SELECT COUNT(*) FROM '+table+' WHERE user_id=1')).scalar(), 0)
            self.assertEqual(c.execute(text('SELECT COUNT(*) FROM user_devices WHERE user_id=1')).scalar(), 0)

    def test_locked_accounts_excluded_from_notification_matching(self):
        self.change(False)
        self.assertEqual([p.user_id for p in notification_service.get_notification_preferences()], [2])

    def test_locked_accounts_cannot_receive_new_notification_records(self):
        self.change(False)
        self.assertFalse(notification_store.save_notification(1, 'https://example.com/b', 'Thể thao'))
        self.change(True)
        self.assertTrue(notification_store.save_notification(1, 'https://example.com/b', 'Thể thao'))

    def test_sender_rejects_locked_account_even_if_a_device_remains(self):
        self.change(False)
        with engine.begin() as c: c.execute(text("INSERT INTO user_devices VALUES(2,1,'stale-device')"))
        with patch.object(sender, 'send_notification') as send:
            self.assertEqual(sender.send_notification_to_user(1, 'Title', 'Body'), 0)
            send.assert_not_called()

    def test_new_accounts_start_active_and_receive_versioned_tokens(self):
        identity = {'uid': 'uid-new', 'email': 'new@example.com'}
        firebase.authenticate.return_value = identity
        response = client.post('/auth/register', json={'email': identity['email'], 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 201)
        created_id = response.json()['user_id']
        self.assertTrue(self.row(created_id)['is_active'])
        response = client.post('/auth/login', json={'email': identity['email'], 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(security.decode_access_token(response.json()['access_token'])['ver'], 0)

    def test_other_users_and_admin_remain_usable(self):
        self.change(False)
        beta = {'Authorization': 'Bearer '+security.create_access_token(2, token_version=0)}
        self.assertEqual(client.get('/auth/me', headers=beta).status_code, 200)
        self.assertEqual(client.get('/admin/users', headers=self.admin_headers).status_code, 200)
        self.assertEqual(client.get('/auth/me', headers=self.admin_headers).status_code, 401)

if __name__ == '__main__': unittest.main(verbosity=2)
