import json
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
import yaml
import hashlib
import base64


def blob_sha(text):
    raw = text.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class MockSession:
    def __init__(self, text):
        self.text = text
        self.calls = []
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        sha = blob_sha(self.text)
        if name == 'get_file_contents':
            content = [
                {'type': 'text', 'text': f'successfully downloaded text file (SHA: {sha})'},
                {'type': 'resource', 'resource': {
                    'uri': 'repo://comvl-cyber/k3s/sha/' + 'a'*40 + '/contents/' + arguments['path'],
                    'text': self.text}},
            ]
        else:
            assert arguments['sha'] == sha
            self.text = base64.b64decode(arguments['content']).decode('utf-8')
            content = [{'type': 'text', 'text': json.dumps({'commit': {'sha': 'b'*40},
                                                         'content': {'sha': blob_sha(self.text)}})}]
        class R:
            def model_dump(self, **kw):
                return {'is_error': False, 'content': content}
        return R()


def test_executor_processes_model_switch_request(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    original_yaml = """apiVersion: v1
kind: ConfigMap
metadata:
  name: honcho-config
  namespace: honcho
  annotations: {}
data:
  EMBEDDING_MODEL_CONFIG__MODEL: baai/bge-m3
  EMBEDDING_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DERIVER_MODEL_CONFIG__TRANSPORT: openai
  DERIVER_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DERIVER_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DERIVER_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  SUMMARY_MODEL_CONFIG__TRANSPORT: openai
  SUMMARY_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  SUMMARY_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  SUMMARY_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
"""

    req_id = 'a' * 32
    now = datetime.now(timezone.utc)
    proof_exp = (now + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    now_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    req = Request(id=req_id, kind='model-switch', status='queued',
                  createdAt=now_str, updatedAt=now_str, submittedBy='admin',
                  payload={'provider': 'openrouter', 'model': 'deepseek/deepseek-chat',
                           'revision': 'a' * 40, 'testedRevision': 'a' * 40,
                           'testedAt': now_str, 'proofExpiresAt': proof_exp,
                           'validation': {'passed': True}})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'a' * 40, original_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(original_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'applied'
    assert 'revision' in processed.result
    write_calls = [c for c in session.calls if c[0] == 'create_or_update_file']
    assert len(write_calls) == 1
    assert write_calls[0][1]['path'] == 'infrastructure/honcho/config.yaml'
    written = yaml.safe_load(session.text)['data']
    assert written['EMBEDDING_MODEL_CONFIG__MODEL'] == 'baai/bge-m3'
    for slot in ['DERIVER_MODEL_CONFIG', 'SUMMARY_MODEL_CONFIG']:
        assert written[slot + '__MODEL'] == 'deepseek/deepseek-chat'
        assert written[slot + '__OVERRIDES__BASE_URL'] == 'https://openrouter.ai/api/v1'
        assert written[slot + '__OVERRIDES__API_KEY_ENV'] == 'OPENROUTER_API_KEY'


def test_executor_rejects_stale_revision(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    original_yaml = """apiVersion: v1
kind: ConfigMap
metadata:
  name: honcho-config
  namespace: honcho
  annotations: {}
data:
  EMBEDDING_MODEL_CONFIG__MODEL: baai/bge-m3
  DERIVER_MODEL_CONFIG__TRANSPORT: openai
  DERIVER_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DERIVER_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DERIVER_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: OPENROUTER_API_KEY
"""

    req_id = 'b' * 32
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    req = Request(id=req_id, kind='model-switch', status='queued',
                  createdAt=now, updatedAt=now, submittedBy='admin',
                  payload={'provider': 'openrouter', 'model': 'deepseek/deepseek-chat',
                           'revision': 'oldrev' + '0' * 36, 'testedRevision': 'oldrev' + '0' * 36,
                           'testedAt': now, 'proofExpiresAt': now,
                           'validation': {'passed': True}})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'newrev' + '0' * 36, original_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(original_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'rejected'
    assert 'revision' in processed.result['message'].lower()


def test_executor_rejects_expired_proof(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    original_yaml = """apiVersion: v1
kind: ConfigMap
metadata:
  name: honcho-config
  namespace: honcho
  annotations: {}
data:
  EMBEDDING_MODEL_CONFIG__MODEL: baai/bge-m3
  DERIVER_MODEL_CONFIG__TRANSPORT: openai
  DERIVER_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DERIVER_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DERIVER_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: OPENROUTER_API_KEY
"""

    req_id = 'c' * 32
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    expired = '2020-01-01T00:00:00Z'
    req = Request(id=req_id, kind='model-switch', status='queued',
                  createdAt=now, updatedAt=now, submittedBy='admin',
                  payload={'provider': 'openrouter', 'model': 'deepseek/deepseek-chat',
                           'revision': 'a' * 40, 'testedRevision': 'a' * 40,
                           'testedAt': expired, 'proofExpiresAt': expired,
                           'validation': {'passed': True}})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'a' * 40, original_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(original_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'rejected'
    assert 'proof expired' in processed.result['message'].lower()


def test_executor_processes_provider_upsert(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    providers_yaml = """# OpenConcho provider config
providers: []
"""

    req_id = 'd' * 32
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    req = Request(id=req_id, kind='provider-upsert', status='queued',
                  createdAt=now, updatedAt=now, submittedBy='admin',
                  payload={'id': 'openai', 'preset': 'openai', 'name': 'OpenAI',
                           'url': 'https://api.openai.com/v1', 'credentialRef': 'OPENAI_API_KEY'})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'a' * 40, providers_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(providers_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'applied'
    written = yaml.safe_load(session.text)
    assert len(written['providers']) == 1
    assert written['providers'][0]['id'] == 'openai'
    assert written['providers'][0]['url'] == 'https://api.openai.com/v1'
    assert written['providers'][0]['credentialRef'] == 'OPENAI_API_KEY'


def test_executor_provider_upsert_rejects_wrong_url(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    providers_yaml = """providers: []"""

    req_id = 'e' * 32
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    req = Request(id=req_id, kind='provider-upsert', status='queued',
                  createdAt=now, updatedAt=now, submittedBy='admin',
                  payload={'id': 'openai', 'preset': 'openai', 'name': 'OpenAI',
                           'url': 'https://wrong.url/v1', 'credentialRef': 'OPENAI_API_KEY'})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'a' * 40, providers_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(providers_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'rejected'
    assert 'url' in processed.result['message'].lower()


def test_executor_model_add(tmp_path):
    from executor.github import GitHubMCP
    from executor.queue import Request
    from executor.executor import process_request

    queue_dir = tmp_path / 'queue'
    queue_dir.mkdir(mode=0o700)

    providers_yaml = """providers:
  - id: openrouter
    preset: openrouter
    name: OpenRouter
    url: https://openrouter.ai/api/v1
    credentialRef: OPENROUTER_API_KEY
library: []"""

    req_id = 'f' * 32
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    req = Request(id=req_id, kind='model-add', status='queued',
                  createdAt=now, updatedAt=now, submittedBy='admin',
                  payload={'provider': 'openrouter', 'model': 'deepseek/deepseek-chat'})
    req.save(queue_dir)

    async def mock_get_revision(path):
        return 'a' * 40, providers_yaml

    async def mock_flux_reconcile():
        pass

    session = MockSession(providers_yaml)
    github = GitHubMCP(session)
    processed = asyncio.run(process_request(req, github, mock_get_revision, mock_flux_reconcile))

    assert processed.status == 'applied'
    written = yaml.safe_load(session.text)
    assert any(e['provider'] == 'openrouter' and e['model'] == 'deepseek/deepseek-chat'
               for e in written['library'])