import unittest
from server import authorize, validate_selection, SLOTS


class SecurityTests(unittest.TestCase):
    def test_rejects_nonstring_provider(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': [], 'model': 'ok'})

    def test_tiny_price_is_unavailable(self):
        from server import price_per_million
        self.assertIsNone(price_per_million('1e-100000'))


    def test_rejects_unknown_provider_url(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': 'http://169.254.169.254', 'model': 'ok'})

    def test_rejects_model_newline(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': 'openrouter', 'model': 'ok\nBAD: true'})

    def test_rejects_forged_identity(self):
        self.assertFalse(authorize({'X-Forwarded-User': 'admin'}, 'admin:$2b$12$invalid'))

class FlowTests(unittest.TestCase):
    def test_pricing_unknown_not_free(self):
        from server import price_per_million
        self.assertIsNone(price_per_million('-1'))

    def test_pricing_conversion(self):
        from server import price_per_million
        self.assertEqual(price_per_million('0.0000002'), '0.2')

    def test_csrf_rejects_cross_origin(self):
        from server import check_csrf
        self.assertFalse(check_csrf({'Origin': 'https://evil.test', 'X-CSRF-Token': 'secret'}, 'secret', 'https://admin.test'))

class ControllerTests(unittest.TestCase):
    def test_catalog_rejects_incomplete_count(self):
        from server import Controller
        from unittest.mock import patch
        with patch('server.provider_request', return_value={'data': [{'id': 'm'}], 'total_count': 2}):
            with self.assertRaises(ValueError):
                Controller().catalog('openrouter')

    def test_structured_test_rejects_plain_string(self):
        from server import valid_answer
        self.assertFalse(valid_answer({'choices': [{'message': {'content': 'hello'}}]}, True))

    def test_structured_test_accepts_expected_object(self):
        from server import valid_answer
        self.assertTrue(valid_answer({'choices': [{'message': {'content': '{"ok":true}'}}]}, True))

    def test_apply_endpoint_is_not_a_write_path(self):
        from server import Controller
        controller = Controller()
        self.assertFalse(hasattr(controller, 'apply'))


if __name__ == '__main__':
    unittest.main()
