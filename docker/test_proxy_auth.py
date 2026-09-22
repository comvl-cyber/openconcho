"""Run the real nginx configuration against hermetic upstream services."""
import http.client
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Upstream(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        self.seen.append(dict(self.headers))
        if self.path == '/admin-api/auth':
            status = 204 if self.headers.get('Cookie') == 'session=valid' else 401
            if status == 204 and self.headers.get('X-Original-Method') not in ('GET', 'HEAD', 'OPTIONS'):
                if self.headers.get('Origin') != 'https://control.example' or self.headers.get('Sec-Fetch-Site') != 'same-origin':
                    status = 403
        else:
            status = 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b'ok')

    def do_POST(self):
        self.do_GET()

    def log_message(self, format, *args):
        pass


class NginxAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        cls.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        root = Path(cls.temp.name)
        root.chmod(0o755)
        cls.port = free_port()
        template = (ROOT / 'docker/nginx.conf.template').read_text()
        template = template.replace('listen       8080;', f'listen 127.0.0.1:{cls.port};')
        template = template.replace('listen       [::]:8080;', '')
        template = template.replace('honcho-model-admin.honcho.svc.cluster.local:8091', f'127.0.0.1:{cls.upstream.server_port}')
        template = template.replace('include /etc/nginx/conf.d/openconcho-api-auth.inc;', 'auth_request /_openconcho_auth;')
        template = template.replace('/usr/share/nginx/html', str(root))
        (root / 'index.html').write_text('Login shell')
        configuration = f'user root; pid {root}/nginx.pid; error_log {root}/error.log; events {{}} http {{ access_log off; map $http_x_honcho_upstream $allow_upstream {{ default 1; }} {template} }}'
        (root / 'nginx.conf').write_text(configuration)
        cls.proc = subprocess.Popen(['nginx', '-p', str(root), '-c', str(root / 'nginx.conf'), '-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError(cls.proc.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=.1):
                    return
            except OSError:
                time.sleep(.05)
        raise RuntimeError('nginx did not listen')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.temp.cleanup()

    def request(self, path, headers=None, method='GET'):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, response.read())
        connection.close()
        return result

    def api_headers(self):
        return {'X-Honcho-Upstream': f'http://127.0.0.1:{self.upstream.server_port}', 'Authorization': 'Basic outer-credential'}

    def test_honcho_api_rejects_basic_only_without_app_session(self):
        self.assertEqual(self.request('/api/health', self.api_headers())[0], 401)

    def test_health_is_public_for_container_probe(self):
        self.assertEqual(self.request('/healthz')[0], 200)

    def test_login_shell_loads_without_application_cookie(self):
        self.assertEqual(self.request('/')[0], 200)

    def test_auth_subrequest_cannot_be_called_directly(self):
        self.assertEqual(self.request('/_openconcho_auth')[0], 404)

    def test_valid_cookie_grants_honcho_access(self):
        self.assertEqual(self.request('/api/health', {**self.api_headers(), 'Cookie': 'session=valid'})[0], 200)

    def test_honcho_upstream_does_not_receive_application_cookie(self):
        self.request('/api/health', {**self.api_headers(), 'Cookie': 'session=valid'})
        self.assertNotIn('Cookie', Upstream.seen[-1])

    def test_cookie_does_not_authorize_cross_origin_post(self):
        headers = {**self.api_headers(), 'Cookie': 'session=valid', 'Origin': 'https://attacker.example', 'Sec-Fetch-Site': 'cross-site'}
        self.assertEqual(self.request('/api/v3/workspaces/list', headers, 'POST')[0], 403)

    def test_same_origin_post_with_cookie_reaches_honcho(self):
        headers = {**self.api_headers(), 'Cookie': 'session=valid', 'Origin': 'https://control.example', 'Sec-Fetch-Site': 'same-origin'}
        self.assertEqual(self.request('/api/v3/workspaces/list', headers, 'POST')[0], 200)

    def test_outer_basic_credential_is_not_forwarded_to_honcho(self):
        self.request('/api/health', {**self.api_headers(), 'Cookie': 'session=valid'})
        self.assertNotIn('Authorization', Upstream.seen[-1])


if __name__ == '__main__':
    unittest.main()
