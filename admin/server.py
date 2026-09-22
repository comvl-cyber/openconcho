"""Private Honcho administration. Never accepts URLs or credentials from clients."""
import base64
import hmac
import json
import os
import re
from passlib.hash import apr_md5_crypt, bcrypt
from auth import Sessions, LoginLimiter, verify_login
from proofs import Proofs
from request_queue import (list_requests, create_request, validate_model_switch,
                      validate_model_add, validate_provider_upsert, load_favorites,
                      ALLOWED_PRESETS)

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


def deployment_is_ready(deployment):
    """Return rollout health from Kubernetes status, independent of config markers."""
    status = deployment.get('status', {})
    desired = deployment.get('spec', {}).get('replicas', 1)
    return (status.get('observedGeneration', 0) >= deployment.get('metadata', {}).get('generation', 0) and
            status.get('updatedReplicas', 0) == desired and
            status.get('availableReplicas', 0) == desired and
            status.get('replicas', 0) == desired)


class Controller:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = Sessions()
        self.login_limiter = LoginLimiter()
        self.proofs = Proofs()
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

    def test(self, body, session):
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
        if not passed:
            return {'revision': revision, 'passed': False, 'results': results,
                    'policy': 'Read-only compatibility check. Model changes are operator-controlled; embeddings remain unchanged.'}
        issued = self.proofs.issue(provider, model, revision, session)
        return {'revision': revision, 'passed': True, 'results': results,
                'policy': 'Read-only compatibility check. Model changes are operator-controlled; embeddings remain unchanged.',
                'proof': issued['proof'], 'testedAt': issued['testedAt'], 'proofExpiresAt': issued['proofExpiresAt']}

    def kube(self, path):
        root = Path('/var/run/secrets/kubernetes.io/serviceaccount')
        return request_json('GET', 'https://kubernetes.default.svc' + path,
            headers={'Authorization': 'Bearer ' + (root/'token').read_text().strip()}, verify=str(root/'ca.crt'))

    def status(self):
        revision, source = self.snapshot()
        config = yaml.safe_load(source)
        data = config['data']
        deployments = []
        for name in ['honcho-api', 'honcho-deriver']:
            deployment = self.kube('/apis/apps/v1/namespaces/honcho/deployments/' + name)
            deployments.append({'name': name, 'ready': deployment_is_ready(deployment)})
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

    def respond(self, status, body, cookie=None):
        encoded = json.dumps(body).encode() if body is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(encoded)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def same_origin(self):
        origin = os.environ.get('ADMIN_ORIGIN')
        return bool(origin and self.headers.get('Origin') == origin and
                    self.headers.get('Sec-Fetch-Site') == 'same-origin')

    def read_body(self):
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            raise ValueError('JSON body required')
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 4096:
            raise ValueError('Body size limit exceeded')
        return json.loads(self.rfile.read(length))

    def session_body(self, session):
        return {'csrf': session['csrf'], 'providers': [
            {'id': p, 'name': v['name'], 'url': v['url'],
             'configured': bool(os.environ.get(v['key_env']) or os.environ.get(v['key_env'] + '_FILE'))}
            for p, v in PROVIDERS.items()]}

    def handle_api(self, mutation=False):
        try:
            path = urlsplit(self.path)
            if not mutation and path.path in ('/health', '/admin-api/health'):
                return self.respond(200, {'status': 'ok'})
            if mutation and path.path == '/admin-api/login':
                if not self.same_origin():
                    return self.respond(403, {'error': 'Same-origin validation failed'})
                client = self.client_address[0]
                ticket = self.controller.login_limiter.reserve(client)
                if ticket is None:
                    return self.respond(429, {'error': 'Invalid username or password'})
                try:
                    body = self.read_body()
                except (ValueError, UnicodeError):
                    return self.respond(401, {'error': 'Invalid username or password'})
                users = Path(os.environ.get('AUTH_FILE', '/auth/users')).read_text()
                if not verify_login(body, users):
                    return self.respond(401, {'error': 'Invalid username or password'})
                self.controller.login_limiter.succeeded(client, ticket)
                self.controller.sessions.revoke(self.headers)
                token, session = self.controller.sessions.create(body['username'])
                return self.respond(200, self.session_body(session), self.controller.sessions.cookie(token))
            session = self.controller.sessions.get(self.headers)
            if not session:
                return self.respond(401, {'error': 'Application authentication required'})
            if not mutation and path.path == '/admin-api/auth':
                original = self.headers.get('X-Original-Method', 'GET')
                if original not in ('GET', 'HEAD', 'OPTIONS') and not self.same_origin():
                    return self.respond(403, {'error': 'Same-origin validation failed'})
                return self.respond(204, None)
            if mutation and not check_csrf(self.headers, session['csrf'], os.environ['ADMIN_ORIGIN']):
                return self.respond(403, {'error': 'Same-origin CSRF validation failed'})
            if mutation and path.path == '/admin-api/logout':
                if self.read_body() != {}:
                    raise ValueError('Logout requires an empty object')
                self.controller.sessions.revoke(self.headers)
                return self.respond(200, {'ok': True}, self.controller.sessions.cookie(''))
            if not mutation and path.path == '/admin-api/session':
                return self.respond(200, self.session_body(session))
            if mutation and path.path == '/admin-api/requests':
                body = self.read_body()
                if not isinstance(body, dict):
                    raise ValueError('Invalid request body')
                if body.get('kind') == 'model-switch':
                    validated = validate_model_switch(body, body.get('provider', ''), self.controller, session)
                elif body.get('kind') == 'model-add':
                    validated = validate_model_add(body, self.controller)
                elif body.get('kind') == 'provider-upsert':
                    validated = validate_provider_upsert(body)
                else:
                    raise ValueError('Unknown request kind')
                result = create_request(body['kind'], validated, session['username'])
                return self.respond(202, {'request': result})
            if not mutation and path.path == '/admin-api/requests':
                favorites = load_favorites()
                provider_presets = [{'id': p['id'], 'name': p['name'], 'url': p['url'], 'credentialRef': p['credentialRef']}
                                    for p in ALLOWED_PRESETS.values()]
                result = {'csrf': session['csrf'], 'providers': [
                    {'id': p, 'name': v['name'], 'url': v['url'],
                     'configured': bool(os.environ.get(v['key_env']) or os.environ.get(v['key_env'] + '_FILE'))}
                    for p, v in PROVIDERS.items()],
                    'providerPresets': provider_presets, 'favorites': favorites,
                    'requests': list_requests()[:50], 'count': len(list_requests())}
                return self.respond(200, result)
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
                        result = self.controller.test(body, session)
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


def reload_providers_from_configmap():
    """Reload provider profiles from PROVIDERS_FILE ConfigMap at runtime.
    Only allows safe keys: id, name, url, credentialRef, secret, secret_key.
    Rejects arbitrary UI URLs or keys."""
    if not os.environ.get('PROVIDERS_FILE'):
        return
    path = Path(os.environ['PROVIDERS_FILE'])
    if not path.exists() or path.stat().st_size == 0:
        return
    try:
        configured = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    for key, profile in configured.items():
        url = urlsplit(profile.get('url', ''))
        if (not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', key) or url.scheme != 'https' or
                not url.hostname or url.username or url.password or url.query or url.fragment or
                url.port not in (None, 443)):
            continue
        # Allow per-provider secret configuration (secret name + key)
        if 'secret' in profile:
            if not re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', profile['secret']):
                continue
        if 'secret_key' in profile:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,62}', profile['secret_key']):
                continue
        # Only update allowed fields
        safe = {k: profile[k] for k in ('name', 'url', 'credentialRef', 'secret', 'secret_key') if k in profile}
        PROVIDERS[key] = {**PROVIDERS.get(key, {}), **safe}
