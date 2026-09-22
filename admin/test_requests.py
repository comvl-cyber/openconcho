"""Test request queue and model/provider management."""
import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from passlib.hash import apr_md5_crypt
from server import Controller, Handler, ThreadingHTTPServer, PROVIDERS


class RequestHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        auth = Path(self.temp.name) / 'users'
        auth.write_text('admin:' + apr_md5_crypt.hash('test-password') + '\n')
        self.env = patch.dict(os.environ, {
            'AUTH_FILE': str(auth), 'ADMIN_ORIGIN': 'https://admin.test',
            'REQUESTS_DIR': str(Path(self.temp.name) / 'requests'),
            'ADMIN_DEV_INSECURE_COOKIE': 'false',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.controller = Controller()
        # Only the external Kubernetes boundary is mocked.
        self.kube_patch = patch.object(self.controller, 'kube', return_value={'data': {}, 'metadata': {'resourceVersion': 'test-rev'}})
        self.kube_patch.start()
        self.addCleanup(self.kube_patch.stop)

        handler = type('TestHandler', (Handler,), {'controller': self.controller})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, cookie=None, csrf=None, headers=None):
        merged = {'Origin': 'https://admin.test', 'Sec-Fetch-Site': 'same-origin'}
        if body is not None:
            merged['Content-Type'] = 'application/json'
        if cookie:
            merged['Cookie'] = cookie
        if csrf:
            merged['X-CSRF-Token'] = csrf
        for key, value in (headers or {}).items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        conn.request(method, path, json.dumps(body) if body is not None else None, merged)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(data) if data else None)
        conn.close()
        return result

    def login(self, cookie=None):
        return self.request('POST', '/admin-api/login',
                            {'username': 'admin', 'password': 'test-password'}, cookie)

    def test_requests_endpoint_requires_auth(self):
        self.assertEqual(self.request('GET', '/admin-api/requests')[0], 401)
        self.assertEqual(self.request('POST', '/admin-api/requests', {})[0], 401)

    def test_requests_endpoint_returns_provider_presets_and_favorites(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, body = self.request('GET', '/admin-api/requests', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn('providerPresets', body)
        self.assertIn('favorites', body)
        self.assertIn('requests', body)
        self.assertIn('count', body)
        presets = {p['id']: p for p in body['providerPresets']}
        self.assertEqual(presets['openrouter']['credentialRef'], 'OPENROUTER_API_KEY')
        self.assertEqual(presets['openrouter']['url'], 'https://openrouter.ai/api/v1')

    def test_model_add_request_queued(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        # First populate catalog with a test model
        with patch('server.provider_request', return_value={'data': [{'id': 'test/model'}], 'total_count': 1}):
            self.controller.catalog('openrouter')
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-add', 'provider': 'openrouter', 'model': 'test/model'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 202)
        self.assertEqual(body['request']['kind'], 'model-add')
        self.assertEqual(body['request']['status'], 'queued')
        self.assertEqual(body['request']['payload']['model'], 'test/model')

    def test_model_add_rejects_unknown_provider(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-add', 'provider': 'unknown', 'model': 'x'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_model_add_rejects_model_not_in_catalog(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        with patch('server.provider_request', return_value={'data': [{'id': 'real/model'}], 'total_count': 1}):
            self.controller.catalog('openrouter')
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-add', 'provider': 'openrouter', 'model': 'fake/model'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_provider_upsert_request_queued(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'provider-upsert', 'preset': 'openrouter',
                                        'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1',
                                        'credentialRef': 'OPENROUTER_API_KEY'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 202)
        self.assertEqual(body['request']['kind'], 'provider-upsert')
        self.assertEqual(body['request']['payload']['preset'], 'openrouter')

    def test_provider_upsert_rejects_mismatched_fields(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'provider-upsert', 'preset': 'openrouter',
                                        'name': 'Wrong', 'url': 'https://other.test/api',
                                        'credentialRef': 'OPENROUTER_API_KEY'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_provider_upsert_rejects_unknown_preset(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'provider-upsert', 'preset': 'unknown',
                                        'name': 'X', 'url': 'https://x.test', 'credentialRef': 'X_KEY'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_model_switch_rejects_forged_proof_even_for_current_catalog(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        with patch('server.provider_request', return_value={'data': [{'id': 'test/model'}], 'total_count': 1}):
            self.controller.catalog('openrouter')
        revision = 'test-rev'
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-switch', 'provider': 'openrouter', 'model': 'test/model',
                                        'revision': revision, 'proof': 'valid-proof'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_model_switch_rejects_stale_revision(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        with patch('server.provider_request', return_value={'data': [{'id': 'test/model'}], 'total_count': 1}):
            self.controller.catalog('openrouter')
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-switch', 'provider': 'openrouter', 'model': 'test/model',
                                        'revision': 'stale', 'proof': 'valid-proof'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)

    def test_model_switch_rejects_model_not_in_catalog(self):
        _, headers, session = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        with patch('server.provider_request', return_value={'data': [{'id': 'real/model'}], 'total_count': 1}):
            self.controller.catalog('openrouter')
        revision = self.controller.snapshot()[0]
        status, _, body = self.request('POST', '/admin-api/requests',
                                       {'kind': 'model-switch', 'provider': 'openrouter', 'model': 'fake/model',
                                        'revision': revision, 'proof': 'valid-proof'},
                                       cookie, session['csrf'])
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()