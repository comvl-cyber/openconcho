import json
import os
import tempfile
import unittest
from unittest.mock import patch
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
    def setUp(self):
        from server import PROVIDERS
        self._saved_providers = dict(PROVIDERS)

    def tearDown(self):
        from server import PROVIDERS
        PROVIDERS.clear()
        PROVIDERS.update(self._saved_providers)

    def test_request_json_reaches_real_local_http_upstream(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from server import request_json

        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                data = json.dumps({'realTransport': True}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream.shutdown)
        try:
            result = request_json('GET', f'http://127.0.0.1:{upstream.server_port}/models')
        except Exception as error:
            result = type(error).__name__
        self.assertEqual(result, {'realTransport': True})

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

    def test_deployment_readiness_does_not_require_model_change_marker(self):
        from server import deployment_is_ready
        self.assertTrue(deployment_is_ready({
            'metadata': {'generation': 11},
            'spec': {'replicas': 1},
            'status': {
                'observedGeneration': 11,
                'updatedReplicas': 1,
                'availableReplicas': 1,
                'replicas': 1,
            },
        }))

    def test_apply_endpoint_is_not_a_write_path(self):
        from server import Controller
        controller = Controller()
        self.assertFalse(hasattr(controller, 'apply'))

    def test_provider_reload_from_configmap_only_allowed_keys(self):
        import tempfile
        from server import PROVIDERS, reload_providers_from_configmap
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'openrouter': {'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1', 'credentialRef': 'OPENROUTER_API_KEY'},
                'newprovider': {'name': 'New', 'url': 'https://new.test/api', 'credentialRef': 'NEW_KEY', 'evil': 'ignored'},
            }, f)
            config_path = f.name
        try:
            with patch.dict(os.environ, {'PROVIDERS_FILE': config_path}):
                reload_providers_from_configmap()
            self.assertIn('newprovider', PROVIDERS)
            self.assertEqual(PROVIDERS['newprovider']['url'], 'https://new.test/api')
            self.assertNotIn('evil', PROVIDERS['newprovider'])
        finally:
            os.unlink(config_path)

    def test_provider_reload_rejects_invalid_url(self):
        import tempfile
        from server import PROVIDERS, reload_providers_from_configmap
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'bad': {'url': 'http://localhost:8080', 'credentialRef': 'KEY'}}, f)
            config_path = f.name
        try:
            with patch.dict(os.environ, {'PROVIDERS_FILE': config_path}):
                reload_providers_from_configmap()
            self.assertNotIn('bad', PROVIDERS)
        finally:
            os.unlink(config_path)


if __name__ == '__main__':
    unittest.main()
