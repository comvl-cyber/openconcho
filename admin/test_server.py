import base64
import unittest
from server import authorize, validate_selection, edit_config, SLOTS


class SecurityTests(unittest.TestCase):
    def test_rejects_nonstring_provider(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': [], 'model': 'ok'})

    def test_tiny_price_is_unavailable(self):
        from server import price_per_million
        self.assertIsNone(price_per_million('1e-100000'))

    def test_rejects_nonstr_token(self):
        from server import require_proof
        with self.assertRaises(ValueError):
            require_proof({}, [], 'openrouter', 'x', 'r')

    def test_rejects_unknown_provider_url(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': 'http://169.254.169.254', 'model': 'ok'})

    def test_rejects_model_newline(self):
        with self.assertRaises(ValueError):
            validate_selection({'provider': 'openrouter', 'model': 'ok\nBAD: true'})

    def test_rejects_forged_identity(self):
        self.assertFalse(authorize({'X-Forwarded-User': 'admin'}, 'admin:$2b$12$invalid'))

    def test_chat_edit_preserves_embeddings(self):
        source = 'data:\n  EMBEDDING_MODEL_CONFIG__MODEL: baai/bge-m3\n' + ''.join(f'  {s}__MODEL: old\n  {s}__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1\n' for s in SLOTS)
        result = edit_config(source, 'new/model', 'openrouter')
        self.assertIn('  EMBEDDING_MODEL_CONFIG__MODEL: baai/bge-m3\n', result)


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

    def test_apply_requires_passing_fresh_test(self):
        from server import require_proof
        with self.assertRaises(ValueError):
            require_proof({}, 'token', 'openrouter', 'model', 'revision')

    def test_apply_rejects_stale_revision(self):
        import time
        from server import require_proof
        with self.assertRaises(ValueError):
            require_proof({'token': {'provider': 'openrouter', 'model': 'model', 'revision': 'old', 'expires': time.time()+60, 'passed': True}}, 'token', 'openrouter', 'model', 'new')

    def test_apply_normalizes_all_structured_modes(self):
        source = 'data:\n' + ''.join(f'  {s}__MODEL: old\n  {s}__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1\n' for s in SLOTS)
        self.assertEqual(edit_config(source, 'model', 'openrouter').count('__STRUCTURED_OUTPUT_MODE: "json_object"'), 9)


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

    def test_apply_never_writes_without_proof(self):
        from server import Controller
        from unittest.mock import patch
        controller = Controller()
        with patch.object(controller, 'snapshot', return_value=('rev', 'data: {}')), patch.object(controller, 'write') as writer:
            with self.assertRaises(ValueError):
                controller.apply({'provider': 'openrouter', 'model': 'm', 'proof': 'fake', 'revision': 'rev', 'confirm': 'm'})
            writer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
