import importlib
import sys
import types
import unittest
from unittest.mock import patch


class NotificationSenderTests(unittest.TestCase):
    def test_background_push_keeps_article_identity_and_brand_icon(self):
        config = types.ModuleType('src.notifications.firebase_config')
        config.firebase_app = object()
        with patch.dict(sys.modules, {'src.notifications.firebase_config': config}):
            sender = importlib.import_module('src.notifications.sender')
        data = {'screen': 'notifications', 'notification_tag': 'newsora_article_42'}
        with patch.object(sender.messaging, 'send', return_value='message-id') as send:
            self.assertEqual(sender.send_notification('device-token', 'Article title', 'Article description', data), 'message-id')
        message = send.call_args.args[0]
        self.assertEqual(message.notification.title, 'Article title')
        self.assertEqual(message.notification.body, 'Article description')
        self.assertEqual(message.android.notification.tag, 'newsora_article_42')
        self.assertEqual(message.android.notification.icon, 'ic_stat_newsora')
        self.assertEqual(message.data, data)


if __name__ == '__main__':
    unittest.main()
