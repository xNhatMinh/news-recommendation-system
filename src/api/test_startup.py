"""Load the actual application with mocked routers to test startup compatibility."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import APIRouter
from fastapi.testclient import TestClient


class StartupTests(unittest.TestCase):
    def load_app(self):
        modules = {}
        for name in ['auth', 'recommendation', 'preferences', 'history', 'summary',
                     'devices', 'articles', 'search', 'bookmarks', 'notifications',
                     'automation', 'terms', 'admin']:
            module = types.ModuleType('src.api.routes.' + name)
            module.router = APIRouter()
            modules[module.__name__] = module
        store = types.ModuleType('src.db.admin_store')
        store.init_admin_tables = Mock()
        modules[store.__name__] = store
        target = Path(__file__).with_name('main.py')
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('startup_test_app', target)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module.app, store.init_admin_tables

    def test_app_import_does_not_initialize_database(self):
        app, initialize = self.load_app()
        initialize.assert_not_called()
        self.assertIsNotNone(app.router.lifespan_context)

    def test_lifespan_initializes_before_serving_health(self):
        app, initialize = self.load_app()
        with TestClient(app) as client:
            initialize.assert_called_once_with()
            self.assertEqual(client.get('/health').json(), {'status': 'ok'})
        initialize.assert_called_once_with()

    def test_startup_failure_does_not_serve_requests(self):
        app, initialize = self.load_app()
        initialize.side_effect = RuntimeError('test initialization failure')
        with self.assertRaises(RuntimeError):
            with TestClient(app):
                self.fail('Startup failure must propagate')


if __name__ == '__main__':
    unittest.main(verbosity=2)
