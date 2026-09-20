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


def edit_config(source, model, provider):
    validate_selection({'provider': provider, 'model': model})
    for slot in SLOTS:
        for suffix, value in [('MODEL', model), ('OVERRIDES__BASE_URL', PROVIDERS[provider]['url'])]:
            source, count = re.subn(r'^  ' + re.escape(slot + '__' + suffix) + r': .*$',
                                    f'  {slot}__{suffix}: {json.dumps(value)}', source, flags=re.M)
            if count != 1:
                raise ValueError('Expected exactly nine configured chat slots')
        key = slot + '__STRUCTURED_OUTPUT_MODE'
        if re.search(r'^  ' + key + ':', source, flags=re.M):
            source = re.sub(r'^  ' + key + ': .*$', f'  {key}: "json_object"', source, flags=re.M)
        else:
            source += f'  {key}: "json_object"\n'
        key = slot + '__OVERRIDES__API_KEY_ENV'
        if re.search(r'^  ' + key + ':', source, flags=re.M):
            source = re.sub(r'^  ' + key + ': .*$', f'  {key}: HONCHO_CHAT_API_KEY', source, flags=re.M)
        else:
            source += f'  {key}: HONCHO_CHAT_API_KEY\n'
    return source


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


def require_proof(proofs, token, provider, model, revision):
    import time
    if not isinstance(token, str) or len(token) > 100:
        raise ValueError('Invalid test proof')
    proof = proofs.get(token, {})
    if not (proof.get('passed') and proof.get('provider') == provider and
            proof.get('model') == model and proof.get('revision') == revision and
            proof.get('expires', 0) > time.time()):
        raise ValueError('Run a successful compatibility test against the current Git revision first')
    return proof


import hashlib
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urljoin
import requests
import yaml

CONFIG_PATH = 'infrastructure/honcho/config.yaml'
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
        self.proofs = {}
        self.catalogs = {}
        self.repo = Path(os.environ.get('GIT_WORKDIR', '/tmp/gitops'))

    def git(self, *args):
        env = dict(os.environ, GIT_SSH_COMMAND='ssh -i /tmp/ssh/identity -o UserKnownHostsFile=/tmp/ssh/known_hosts -o IdentitiesOnly=yes')
        result = subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True,
                                timeout=30, check=False, env=env)
        if result.returncode:
            raise ValueError('Git operation failed; check deploy-key access or concurrent remote changes') from None
        return result.stdout.decode().strip()

    def snapshot(self):
        if not (self.repo / '.git').exists():
            self.repo.mkdir(parents=True, exist_ok=True)
            self.git('init')
            remote = os.environ.get('GIT_REMOTE')
            if not remote or not re.match(r'^(https?://|git@)', remote):
                raise ValueError('GIT_REMOTE must be a valid HTTPS or SSH git URL')
            self.git('remote', 'add', 'origin', remote)
            self.git('config', 'user.name', 'OpenConcho Model Admin')
            self.git('config', 'user.email', 'openconcho-model-admin@users.noreply.github.com')
        self.git('fetch', '--depth=2', 'origin', 'main')
        self.git('checkout', '-B', 'main', 'FETCH_HEAD')
        return self.git('rev-parse', 'HEAD'), (self.repo / CONFIG_PATH).read_text()

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
        token = secrets.token_urlsafe(32)
        self.proofs = {k:v for k,v in self.proofs.items() if v['expires'] > time.time()}
        self.proofs[token] = {'provider': provider, 'model': model, 'revision': revision,
                              'expires': time.time()+600, 'passed': passed}
        return {'proof': token, 'revision': revision, 'passed': passed, 'results': results,
                'policy': 'Apply sets all nine chat slots to tested json_object; reasoning, temperature and budgets are retained. Embeddings unchanged.'}

    def write(self, source, provider, model, revision):
        # Cross-process lock: single-writer via git branch + atomic push (force-with-lease)
        # This avoids fcntl which only locks within a single process.
        self.git('checkout', '-B', 'model-update', 'FETCH_HEAD')
        self.git('push', '--force-with-lease', 'origin', 'HEAD:refs/heads/model-update')
        # Re-fetch to get the remote state after our force-with-lease push
        self.git('fetch', '--depth=1', 'origin', 'main')
        # Merge our branch into main locally
        self.git('merge', '--ff-only', 'model-update')

        old = yaml.safe_load(source)
        current_model = old['data'][SLOTS[0]+'__MODEL']
        current_url = old['data'][SLOTS[0]+'__OVERRIDES__BASE_URL']
        previous_provider = next((p for p,v in PROVIDERS.items() if v['url'] == current_url), None)
        if previous_provider is None or any(old['data'][s+'__MODEL'] != current_model for s in SLOTS):
            raise ValueError('Nonuniform current configuration requires operator review')
        updated = edit_config(source, model, provider)
        # Store rollback MODEL identity in Git (never keys); rollback is re-tested.
        doc = yaml.safe_load(updated)
        annotations = doc['metadata'].setdefault('annotations', {})
        annotations['openconcho.io/previous-model'] = current_model
        annotations['openconcho.io/previous-provider'] = previous_provider
        marker = secrets.token_hex(12)
        annotations[ANNOTATION] = marker
        # Keep existing data lines byte-preserved, changing only metadata and selected chat settings.
        metadata_end = updated.index('data:\n')
        updated = yaml.safe_dump({k:v for k,v in doc.items() if k != 'data'}, sort_keys=False) + updated[metadata_end:]
        (self.repo / CONFIG_PATH).write_text(updated)
        profile = PROVIDERS[provider]
        for filename in ['api.yaml', 'deriver.yaml']:
            path = self.repo / 'infrastructure/honcho' / filename
            docs = list(yaml.safe_load_all(path.read_text()))
            for deployment in docs:
                if deployment['kind'] != 'Deployment':
                    continue
                template = deployment['spec']['template']
                template['metadata'].setdefault('annotations', {})[ANNOTATION] = marker
                env = template['spec']['containers'][0].setdefault('env', [])
                for name in ['HONCHO_CHAT_API_KEY']:
                    env[:] = [item for item in env if item['name'] != name]
                    secret_name = profile.get('secret', 'honcho-openrouter')
                    secret_key = profile.get('secret_key', 'OPENROUTER_API_KEY')
                    env.append({'name': name, 'valueFrom': {'secretKeyRef': {
                        'name': secret_name, 'key': secret_key}}})
            path.write_text(yaml.safe_dump_all(docs, sort_keys=False))
        # Atomic push with force-with-lease ensures no lost updates
        self.git('add', CONFIG_PATH, 'infrastructure/honcho/api.yaml', 'infrastructure/honcho/deriver.yaml')
        self.git('commit', '-m', f'feat(honcho): select {provider} model {model}')
        commit = self.git('rev-parse', 'HEAD')
        self.git('push', '--force-with-lease', 'origin', 'HEAD:refs/heads/main')
        remote = self.git('ls-remote', 'origin', 'refs/heads/main').split()[0]
        if remote != commit:
            raise ValueError('Remote advanced after push; refresh status before proceeding')
        return {'commit': commit, 'model': model, 'provider': provider, 'state': 'Awaiting Flux reconciliation'}

    def apply(self, body):
        provider, model = validate_selection(body)
        revision, source = self.snapshot()
        if body.get('revision') != revision or body.get('confirm') != model:
            raise ValueError('Confirmation or Git revision changed; refresh and re-test')
        require_proof(self.proofs, body.get('proof'), provider, model, revision)
        if body.get('rollback'):
            annotations = yaml.safe_load(source)['metadata'].get('annotations', {})
            if (provider, model) != (annotations.get('openconcho.io/previous-provider'), annotations.get('openconcho.io/previous-model')):
                raise ValueError('Rollback target changed; refresh')
        result = self.write(source, provider, model, revision)
        self.proofs.clear()
        return result

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
        live = self.kube('/api/v1/namespaces/honcho/configmaps/honcho-config')['data']
        synced = all(live.get(s+'__MODEL') == data[s+'__MODEL'] and live.get(s+'__OVERRIDES__BASE_URL') == data[s+'__OVERRIDES__BASE_URL'] for s in SLOTS)
        return {'revision': revision, 'model': data[SLOTS[0]+'__MODEL'],
                'slots': {s:data[s+'__MODEL'] for s in SLOTS},
                'provider': next((p for p,v in PROVIDERS.items() if v['url'] == data[SLOTS[0]+'__OVERRIDES__BASE_URL']), 'unknown'),
                'previous': {'model': annotations.get('openconcho.io/previous-model'), 'provider': annotations.get('openconcho.io/previous-provider')},
                'deployments': deployments, 'synced': synced,
                'state': 'Ready' if synced and all(d['ready'] for d in deployments) else 'Awaiting Flux / rollout',
                'embedding': live.get('EMBEDDING_MODEL_CONFIG__MODEL')}


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
                    elif path.path == '/admin-api/apply':
                        result = self.controller.apply(body)
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
            self.respond(503, {'error': 'Administration unavailable; check server configuration, Git access or upstream health'})

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
