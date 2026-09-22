"""Hermetic HTTP integration: real Handler, Controller and requests transport.

Only external HTTP destinations and the Kubernetes credential boundary are
substituted. No catalog, snapshot, compatibility or queue logic is mocked.
"""
import json
import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import requests
import server
import test_sessions


class SecurityHTTPTests(unittest.TestCase):
    request = test_sessions.SessionHTTPTests.request
    login = test_sessions.SessionHTTPTests.login

    def setUp(self):
        test_sessions.SessionHTTPTests.setUp(self)
        self.revision = 'rv-123'
        self.chat_bodies = []
        self.chat_ok = True
        self.change_revision_during_chat = False
        case = self

        class Upstream(BaseHTTPRequestHandler):
            def respond(self, body):
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == '/config':
                    data = {slot + '__MAX_OUTPUT_TOKENS': str(1024 + i)
                            for i, slot in enumerate(server.SLOTS)}
                    self.respond({'metadata': {'resourceVersion': case.revision}, 'data': data})
                else:
                    self.respond({'data': [{'id': 'test/model'}, {'id': 'test/other'}], 'total_count': 2})

            def do_POST(self):
                case.chat_bodies.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if case.change_revision_during_chat:
                    case.revision = 'rv-changed'
                self.respond({'choices': [{'message': {'content': '{"ok":true}' if case.chat_ok else 'not JSON'}}]})

            def log_message(self, format, *args):
                pass

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream.shutdown)
        self.upstream_url = f'http://127.0.0.1:{upstream.server_port}'
        original_send = requests.sessions.Session.send

        def local_send(session, prepared, **kwargs):
            # Reroute only the external network seam; requests.request and all
            # application serialization/parsing still execute unchanged.
            if urlsplit(prepared.url).hostname == 'openrouter.ai':
                prepared.url = case.upstream_url + urlsplit(prepared.url).path
            return original_send(session, prepared, **kwargs)

        for context in (
            patch('requests.sessions.Session.send', new=local_send),
            patch.object(self.controller, 'kube', side_effect=lambda path: server.request_json('GET', self.upstream_url + '/config')),
            patch.dict(os.environ, {'OPENROUTER_API_KEY': 'hermetic-test-credential', 'OPENROUTER_API_KEY_FILE': ''}),
        ):
            context.start()
            self.addCleanup(context.stop)
        status, headers, self.session = self.login()
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';', 1)[0]

    def run_compatibility(self):
        status, _, result = self.request('POST', '/admin-api/test',
                                        {'provider': 'openrouter', 'model': 'test/model'},
                                        self.cookie, self.session['csrf'])
        self.assertEqual(status, 200, result)
        return result

    def switch(self, result, **overrides):
        payload = {'kind': 'model-switch', 'provider': 'openrouter', 'model': 'test/model',
                   'revision': result['revision'], 'proof': result.get('proof', 'missing')}
        payload.update(overrides)
        return self.request('POST', '/admin-api/requests', payload, self.cookie, self.session['csrf'])

    def test_full_real_http_test_issues_single_use_proof(self):
        result = self.run_compatibility()
        self.assertTrue(result['passed'])
        self.assertRegex(result.get('proof', ''), r'^[A-Za-z0-9_-]{43}$')
        self.assertEqual(len(self.chat_bodies), len(server.SLOTS) + 1)
        status, _, queued = self.switch(result)
        self.assertEqual(status, 202, queued)
        payload = queued['request']['payload']
        self.assertEqual(payload, {'provider': 'openrouter', 'model': 'test/model',
                                  'revision': 'rv-123', 'testedRevision': 'rv-123',
                                  'testedAt': result['testedAt'], 'proofExpiresAt': result['proofExpiresAt'],
                                  'validation': {'passed': True}})
        raw = next(Path(os.environ['REQUESTS_DIR']).glob('*.json')).read_text()
        self.assertNotIn(result['proof'], raw)
        self.assertEqual(self.switch(result)[0], 400)


if __name__ == '__main__':
    unittest.main()
