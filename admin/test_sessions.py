"""HTTP boundary tests: only the application cookie authenticates users."""
import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from passlib.hash import apr_md5_crypt
from server import Controller, Handler, ThreadingHTTPServer


class SessionHTTPTests(unittest.TestCase):
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

    def test_login_failures_are_generic_and_rate_limited(self):
        outcomes = [self.request('POST', '/admin-api/login', body,
                    headers={'X-Forwarded-For': f'192.0.2.{index}'})
                    for index, body in enumerate([
                        {'username': 'missing', 'password': 'wrong'},
                        {'username': 'admin', 'password': 'wrong'},
                        [], {}, {'username': 'admin', 'password': 'wrong'},
                        {'username': 'admin', 'password': 'test-password'},
                    ])]
        self.assertEqual([(status, body) for status, _, body in outcomes],
                         [(401, {'error': 'Invalid username or password'})] * 5 +
                         [(429, {'error': 'Invalid username or password'})])

    def test_rotation_revokes_old_cookie(self):
        _, headers, _ = self.login()
        old = headers['Set-Cookie'].split(';', 1)[0]
        self.login(old)
        self.assertEqual(self.request('GET', '/admin-api/session', cookie=old)[0], 401)

    def test_logout_revokes_session(self):
        _, headers, body = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        status, _, _ = self.request('POST', '/admin-api/logout', {}, cookie, body['csrf'])
        self.assertEqual((status, self.request('GET', '/admin-api/session', cookie=cookie)[0]), (200, 401))

    def test_session_expires_when_idle(self):
        with patch('auth.time.monotonic', return_value=100):
            _, headers, _ = self.login()
        with patch('auth.time.monotonic', return_value=100 + 1801):
            status, _, _ = self.request('GET', '/admin-api/session', cookie=headers['Set-Cookie'].split(';', 1)[0])
        self.assertEqual(status, 401)

    def test_session_expires_absolutely_despite_activity(self):
        with patch('auth.time.monotonic', return_value=100):
            _, headers, _ = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        for offset in range(1700, 28801, 1700):
            with patch('auth.time.monotonic', return_value=100 + offset):
                self.request('GET', '/admin-api/session', cookie=cookie)
        with patch('auth.time.monotonic', return_value=100 + 28801):
            status, _, _ = self.request('GET', '/admin-api/session', cookie=cookie)
        self.assertEqual(status, 401)

    def test_auth_request_allows_cookie_only(self):
        _, headers, _ = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        self.assertEqual(self.request('GET', '/admin-api/auth', cookie=cookie)[0], 204)

    def test_auth_request_validates_unsafe_original_method(self):
        _, headers, _ = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        codes = [self.request('GET', '/admin-api/auth', cookie=cookie, headers=h)[0] for h in [
            {'X-Original-Method': 'POST'},
            {'X-Original-Method': 'POST', 'Origin': 'https://evil.test'},
            {'X-Original-Method': 'DELETE', 'Sec-Fetch-Site': None},
            {'X-Original-Method': 'GET', 'Origin': None, 'Sec-Fetch-Site': None},
        ]]
        self.assertEqual(codes, [204, 403, 403, 204])

    def test_health_is_public(self):
        self.assertEqual(self.request('GET', '/health')[0], 200)

    def test_basic_never_authenticates_session(self):
        basic = base64.b64encode(b'admin:test-password').decode()
        self.assertEqual(self.request('GET', '/admin-api/session', headers={'Authorization': 'Basic ' + basic})[0], 401)

    def test_login_origin_and_fetch_site_required(self):
        outcomes = []
        for headers in [{'Origin': None}, {'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': None}, {'Sec-Fetch-Site': 'same-site'}]:
            outcomes.append(self.request('POST', '/admin-api/login', {'username': 'admin', 'password': 'test-password'}, headers=headers)[0])
        self.assertEqual(outcomes, [403] * 4)

    def test_logout_requires_session_csrf(self):
        _, headers, _ = self.login()
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        self.assertEqual(self.request('POST', '/admin-api/logout', {}, cookie)[0], 403)

    def test_login_creates_session_cookie(self):
        status, headers, _ = self.login()
        cookie = headers.get('Set-Cookie', '').split(';', 1)[0]
        self.assertEqual((status, self.request('GET', '/admin-api/session', cookie=cookie)[0]), (200, 200))


if __name__ == '__main__':
    unittest.main()
