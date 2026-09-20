"""Private Honcho administration. Never accepts URLs or credentials from clients."""
import base64
import hmac
import json
import os
import re
from passlib.hash import apr_md5_crypt, bcrypt

SLOTS = ['DERIVER_MODEL_CONFIG', 'SUMMARY_MODEL_CONFIG',
         'DREAM_DEDUCTION_MODEL_CONFIG', 'DREAM_INDUCTION_MODEL_CONFIG'] + [
             f'DIALECTIC_LEVELS__{level}__MODEL_CONFIG' for level in ['minimal', 'low', 'medium', 'high', 'max']]
PROVIDERS = {'openrouter': {'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1',
                            'key_env': 'OPENROUTER_API_KEY', 'pricing': 'openrouter'}}


def validate_selection(body):
    if not isinstance(body, dict) or not isinstance(body.get('provider'), str) or body['provider'] not in PROVIDERS:
        raise ValueError('Choose a configured provider')
    model = body.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9~][A-Za-z0-9._:/@+~-]{0,127}', model):
        raise ValueError('Invalid model identifier')
    return body['provider'], model


def authorize(headers, users):
    try:
        scheme, token = headers.get('Authorization', '').split(' ', 1)
        if scheme != 'Basic' or len(token) > 2048:
            return False
        user, password = base64.b64decode(token, validate=True).decode().split(':', 1)
        for entry in users.splitlines():
            name, hashed = entry.split(':', 1)
            if hmac.compare_digest(user.encode(), name.encode()):
                return (apr_md5_crypt if hashed.startswith('$apr1$') else bcrypt).verify(password, hashed)
    except (ValueError, TypeError, UnicodeError):
        pass
    return False


def price_per_million(value):
    from decimal import Decimal, InvalidOperation
    try:
        if len(str(value)) > 40:
            return None
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > 1000 or number.as_tuple().exponent < -18:
            return None
        return format((number * 1000000).normalize(), 'f')
    except (InvalidOperation, ValueError):
        return None


def check_csrf(headers, token, origin):
    # Require explicit same-origin; absent header fails (no default).
    return (headers.get('Origin') == origin and
            headers.get('Sec-Fetch-Site') == 'same-origin' and
            hmac.compare_digest(headers.get('X-CSRF-Token', ''), token))


import secrets
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urljoin
import requests
import yaml

ANNOTATION = 'openconcho.io/model-change'
MAX_RESPONSE = 8 * 1024 * 1024


def request_json(method, url, **kwargs):
    # No redirects: an upstream cannot redirect credentials to a different host.
    with requests.request(method, url, timeout=(5, 45), allow_redirects=False,
                          stream=True, **kwargs) as response:
        if response.status_code >= 300:
            raise ValueError(f'Upstream HTTP {response.status_code}; response body withheld')
        content = bytearray()
        deadline = time.monotonic() + 50
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > MAX_RESPONSE or time.monotonic() > deadline:
                raise ValueError('Upstream response exceeded safety limits')
        try:
            return json.loads(content)
        except ValueError:
            raise ValueError('Upstream returned invalid JSON') from None


def provider_request(provider, path, payload=None):
    profile = PROVIDERS[provider]
    key = os.environ.get(profile['key_env'])
    key_file = os.environ.get(profile.get('key_file_env', profile['key_env'] + '_FILE'))
    if key_file:
        try:
            key = Path(key_file).read_text().strip()
        except OSError:
            key = None
    if not key:
        raise ValueError('Provider credential is not configured on the server')
    return request_json('POST' if payload else 'GET', profile['url'] + path,
                        headers={'Authorization': 'Bearer ' + key},
                        **({'json': payload} if payload else {}))


def valid_answer(response, structured):
    try:
        text = response['choices'][0]['message']['content']
        return json.loads(text) == {'ok': True} if structured else bool(text and text.strip())
    except (KeyError, IndexError, TypeError, ValueError):
        return False


class Controller:
    def __init__(self):
        self.lock = threading.Lock()
        self.csrf = secrets.token_urlsafe(32)
        self.catalogs = {}

    def snapshot(self):
        config = self.kube('/api/v1/namespaces/honcho/configmaps/honcho-config')
        data = config.get('data')
        if not isinstance(data, dict):
            raise ValueError('Live Honcho configuration is unavailable')
        metadata = config.get('metadata') or {}
        revision = metadata.get('resourceVersion') or metadata.get('uid') or 'live'
        return revision, yaml.safe_dump(config, sort_keys=False)

    def catalog(self, provider):
        if provider not in PROVIDERS:
            raise ValueError('Choose a configured provider')
        models = {}
        path = '/models'
        total = None
        for _ in range(10):
            response = provider_request(provider, path)
            rows = response.get('data')
            if not isinstance(rows, list):
                raise ValueError('Provider model catalog is not an array')
            total = response.get('total_count', total)
            for item in rows:
                if not isinstance(item, dict):
                    raise ValueError('Malformed model catalog entry')
                model = item.get('id')
                validate_selection({'provider': provider, 'model': model})
                pricing = item.get('pricing') or {}
                known = PROVIDERS[provider].get('pricing') == 'openrouter'
                models[model] = {'id': model, 'name': item.get('name', model),
                    'input': price_per_million(pricing.get('prompt')) if known else None,
                    'output': price_per_million(pricing.get('completion')) if known else None,
                    'cache': price_per_million(pricing.get('input_cache_read')) if known else None,
                    'context': item.get('context_length'),
                    'parameters': item.get('supported_parameters') or []}
            links = response.get('links') or {}
            next_url = links.get('next') if isinstance(links, dict) else None
            if not next_url:
                break
            url = urlsplit(urljoin(PROVIDERS[provider]['url'] + '/models', next_url))
            base = urlsplit(PROVIDERS[provider]['url'] + '/models')
            if (url.scheme, url.netloc, url.path) != (base.scheme, base.netloc, base.path):
                raise ValueError('Provider returned an untrusted pagination URL')
            path = '/models' + ('?' + url.query if url.query else '')
        else:
            raise ValueError('Catalog pagination safety limit reached; no partial catalog published')
        if total is not None and (not isinstance(total, int) or len(models) != total):
            raise ValueError('Provider catalog count mismatch; refresh before choosing a model')
        result = {'models': sorted(models.values(), key=lambda row: row['id']),
                  'count': len(models), 'currency': 'USD' if PROVIDERS[provider].get('pricing') == 'openrouter' else None,
                  'source': PROVIDERS[provider]['url'] + '/models',
                  'fetchedAt': datetime.now(timezone.utc).isoformat()}
        self.catalogs[provider] = (time.time(), result)
        return result

    def test(self, body):
        provider, model = validate_selection(body)
        revision, source = self.snapshot()
        cached = self.catalogs.get(provider)
        catalog = cached[1] if cached and time.time() - cached[0] < 300 else self.catalog(provider)
        if model not in {row['id'] for row in catalog['models']}:
            raise ValueError('Model is absent from the current provider catalog')
        data = yaml.safe_load(source)['data']
        profiles = []
        for slot in SLOTS:
            profile = {'max_tokens': int(data.get(slot + '__MAX_OUTPUT_TOKENS',
                data.get(slot.replace('__MODEL_CONFIG', '') + '__MAX_OUTPUT_TOKENS', '2048')))}
            if slot + '__THINKING_EFFORT' in data:
                profile['reasoning_effort'] = data[slot + '__THINKING_EFFORT']
            if slot + '__TEMPERATURE' in data:
                profile['temperature'] = float(data[slot + '__TEMPERATURE'])
            if profile not in profiles:
                profiles.append(profile)
        results = []
        # Plain chat + every distinct production budget/reasoning/temperature combination.
        cases = [('plain', profiles[0], False)] + [(f'json_object {i+1}', p, True) for i,p in enumerate(profiles)]
        deadline = time.monotonic() + 240
        for label, profile, structured in cases:
            if time.monotonic() > deadline:
                results.append({'name': label, 'passed': False, 'detail': 'Overall test time limit reached'})
                break
            payload = {'model': model, **profile, 'messages': [
                {'role': 'system', 'content': 'Return a JSON object with exactly one property: ok, boolean true. No other text.'},
                {'role': 'user', 'content': 'Return {"ok":true} as JSON.'}]}
            if structured:
                payload['response_format'] = {'type': 'json_object'}
            started = time.monotonic()
            try:
                response = provider_request(provider, '/chat/completions', payload)
                passed = valid_answer(response, structured)
                detail = 'Validated response' if passed else 'Missing content or unexpected JSON shape'
            except (ValueError, requests.RequestException):
                passed, detail = False, 'Provider rejected request or timed out; no provider response body exposed'
            results.append({'name': label, 'parameters': profile, 'passed': passed,
                            'detail': detail, 'milliseconds': round((time.monotonic()-started)*1000)})
            if structured and not passed:
                break
        passed = len(results) == len(cases) and all(row['passed'] for row in results)
        return {'revision': revision, 'passed': passed, 'results': results,
                'policy': 'Read-only compatibility check. Model changes are operator-controlled; embeddings remain unchanged.'}

    def kube(self, path):
        root = Path('/var/run/secrets/kubernetes.io/serviceaccount')
        return request_json('GET', 'https://kubernetes.default.svc' + path,
            headers={'Authorization': 'Bearer ' + (root/'token').read_text().strip()}, verify=str(root/'ca.crt'))

    def status(self):
        revision, source = self.snapshot()
        config = yaml.safe_load(source)
        data = config['data']
        annotations = config['metadata'].get('annotations', {})
        marker = annotations.get(ANNOTATION)
        deployments = []
        for name in ['honcho-api', 'honcho-deriver']:
            deployment = self.kube('/apis/apps/v1/namespaces/honcho/deployments/' + name)
            status = deployment.get('status', {})
            live_marker = deployment['spec']['template']['metadata'].get('annotations', {}).get(ANNOTATION)
            ready = (status.get('observedGeneration', 0) >= deployment['metadata']['generation'] and
                     status.get('updatedReplicas', 0) == deployment['spec'].get('replicas', 1) and
                     status.get('availableReplicas', 0) == deployment['spec'].get('replicas', 1) and
                     status.get('replicas', 0) == deployment['spec'].get('replicas', 1) and live_marker == marker)
            deployments.append({'name': name, 'ready': ready})
        return {'revision': revision, 'model': data[SLOTS[0]+'__MODEL'],
                'slots': {s:data[s+'__MODEL'] for s in SLOTS},
                'provider': next((p for p,v in PROVIDERS.items() if v['url'] == data[SLOTS[0]+'__OVERRIDES__BASE_URL']), 'unknown'),
                'deployments': deployments, 'synced': True,
                'state': 'Ready' if all(d['ready'] for d in deployments) else 'Awaiting rollout',
                'embedding': data.get('EMBEDDING_MODEL_CONFIG__MODEL')}


class Handler(BaseHTTPRequestHandler):
    controller = Controller()
    protocol_version = 'HTTP/1.0'

    def log_message(self, format, *args):
        pass  # Never log request headers, bodies, provider output or credentials.

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def respond(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(encoded)))
        if status == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="Honcho administration", charset="UTF-8"')
        self.end_headers()
        self.wfile.write(encoded)

    def handle_api(self, mutation=False):
        try:
            path = urlsplit(self.path)
            if not mutation and path.path == '/admin-api/health':
                return self.respond(200, {'status': 'ok'})
            users = Path(os.environ.get('AUTH_FILE', '/auth/users')).read_text()
            if not authorize(self.headers, users):
                return self.respond(401, {'error': 'Administrator authentication required'})
            if mutation and not check_csrf(self.headers, self.controller.csrf, os.environ['ADMIN_ORIGIN']):
                return self.respond(403, {'error': 'Same-origin CSRF validation failed'})
            if not mutation and path.path == '/admin-api/session':
                return self.respond(200, {'csrf': self.controller.csrf, 'providers': [
                    {'id': p, 'name': v['name'], 'configured': bool(os.environ.get(v['key_env']))}
                    for p,v in PROVIDERS.items()]})
            if not self.controller.lock.acquire(blocking=False):
                return self.respond(409, {'error': 'Another administrative operation is running; retry shortly'})
            try:
                if mutation:
                    if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                        return self.respond(415, {'error': 'JSON body required'})
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4096:
                        return self.respond(413, {'error': 'Body size limit exceeded'})
                    body = json.loads(self.rfile.read(length))
                    if path.path == '/admin-api/test':
                        result = self.controller.test(body)
                    else:
                        return self.respond(404, {'error': 'Not found'})
                elif path.path == '/admin-api/catalog':
                    provider = parse_qs(path.query).get('provider', ['openrouter'])[0]
                    result = self.controller.catalog(provider)
                elif path.path == '/admin-api/status':
                    result = self.controller.status()
                else:
                    return self.respond(404, {'error': 'Not found'})
                self.respond(200, result)
            finally:
                self.controller.lock.release()
        except ValueError as error:
            self.respond(400, {'error': str(error) if len(str(error)) < 200 else 'Invalid request'})
        except Exception:
            self.respond(503, {'error': 'Administration unavailable; check server configuration or upstream health'})

    def do_GET(self):
        self.handle_api()

    def do_POST(self):
        self.handle_api(True)


if __name__ == '__main__':
    # Profiles are operator-owned deployment configuration, not browser input.
    if os.environ.get('PROVIDERS_FILE'):
        configured = json.loads(Path(os.environ['PROVIDERS_FILE']).read_text())
        for key, profile in configured.items():
            url = urlsplit(profile['url'])
            if (not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', key) or url.scheme != 'https' or
                    not url.hostname or url.username or url.password or url.query or url.fragment or
                    url.port not in (None, 443)):
                raise ValueError('Invalid trusted provider profile')
            # Allow per-provider secret configuration (secret name + key)
            if 'secret' in profile:
                if not re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', profile['secret']):
                    raise ValueError('Invalid secret name in provider profile')
            if 'secret_key' in profile:
                if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,62}', profile['secret_key']):
                    raise ValueError('Invalid secret key in provider profile')
        PROVIDERS.update(configured)
    ThreadingHTTPServer(('0.0.0.0', 8091), Handler).serve_forever()
