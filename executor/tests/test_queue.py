import json
import pytest
import tempfile
import os
from pathlib import Path


def test_request_file_structure():
    """Request file has exact fields from contract."""
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ('a' * 32 + '.json')
        data = {
            'id': 'a' * 32,
            'kind': 'model-switch',
            'status': 'queued',
            'createdAt': '2026-01-01T00:00:00Z',
            'updatedAt': '2026-01-01T00:00:00Z',
            'submittedBy': 'admin',
            'payload': {
                'provider': 'openrouter',
                'model': 'deepseek/deepseek-chat',
                'revision': '123',
                'testedRevision': '123',
                'testedAt': '2026-01-01T00:00:00Z',
                'proofExpiresAt': '2026-01-01T01:00:00Z',
                'validation': {'passed': True}
            }
        }
        path.write_text(json.dumps(data))
        req = Request.load(path)
        assert req.id == 'a' * 32
        assert req.kind == 'model-switch'
        assert req.payload['model'] == 'deepseek/deepseek-chat'


def test_request_rejects_missing_fields():
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'req1.json'
        data = {'id': 'a' * 32, 'kind': 'model-switch'}
        path.write_text(json.dumps(data))
        with pytest.raises(Refused):
            Request.load(path)


def test_request_rejects_invalid_kind():
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'req1.json'
        data = {'id': 'a' * 32, 'kind': 'unknown', 'status': 'queued',
                'createdAt': '2026-01-01T00:00:00Z', 'updatedAt': '2026-01-01T00:00:00Z',
                'submittedBy': 'admin', 'payload': {}}
        path.write_text(json.dumps(data))
        with pytest.raises(Refused):
            Request.load(path)


def test_request_rejects_invalid_status():
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'req1.json'
        data = {'id': 'a' * 32, 'kind': 'model-switch', 'status': 'invalid',
                'createdAt': '2026-01-01T00:00:00Z', 'updatedAt': '2026-01-01T00:00:00Z',
                'submittedBy': 'admin', 'payload': {}}
        path.write_text(json.dumps(data))
        with pytest.raises(Refused):
            Request.load(path)


def test_request_rejects_non_hex_id():
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'req1.json'
        data = {'id': 'not-hex', 'kind': 'model-switch', 'status': 'queued',
                'createdAt': '2026-01-01T00:00:00Z', 'updatedAt': '2026-01-01T00:00:00Z',
                'submittedBy': 'admin', 'payload': {}}
        path.write_text(json.dumps(data))
        with pytest.raises(Refused):
            Request.load(path)


def test_request_atomic_write():
    """Request file is written atomically with mode 0600."""
    from executor.queue import Request, Refused
    with tempfile.TemporaryDirectory() as d:
        dir_path = Path(d)
        # Ensure dir mode 0700
        os.chmod(dir_path, 0o700)
        req = Request(id='b' * 32, kind='model-add', status='queued',
                      createdAt='2026-01-01T00:00:00Z', updatedAt='2026-01-01T00:00:00Z',
                      submittedBy='admin', payload={'provider': 'openrouter', 'model': 'm'})
        req.save(dir_path)
        path = dir_path / ('b' * 32 + '.json')
        assert path.exists()
        stat = path.stat()
        assert stat.st_mode & 0o777 == 0o600
        loaded = Request.load(path)
        assert loaded.id == req.id


def test_queue_scan_sorted_newest_first():
    from executor.queue import scan_queue, Request
    with tempfile.TemporaryDirectory() as d:
        dir_path = Path(d)
        os.chmod(dir_path, 0o700)
        for i in range(3):
            ts = f'2026-01-01T00:0{i}:00Z'
            req = Request(id=f'{i:02d}' + 'a'*30, kind='model-add', status='queued',
                          createdAt=ts, updatedAt=ts, submittedBy='admin',
                          payload={'provider': 'openrouter', 'model': 'm'})
            req.save(dir_path)
        reqs = scan_queue(dir_path)
        assert [r.id for r in reqs] == ['02' + 'a'*30, '01' + 'a'*30, '00' + 'a'*30]