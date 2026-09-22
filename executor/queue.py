"""Request queue file I/O. Atomic writes, mode 0600 files, 0700 dir."""
import json
import re
import os
import fcntl
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

VALID_KINDS = frozenset(('model-switch', 'model-add', 'provider-upsert'))
VALID_STATUSES = frozenset(('queued', 'running', 'applied', 'rejected', 'failed'))
HEX32 = re.compile(r'^[a-f0-9]{32}$')
ISO8601 = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


class Refused(ValueError):
    """Safe, operator-facing reason."""


@dataclass
class Request:
    id: str
    kind: str
    status: str
    createdAt: str
    updatedAt: str
    submittedBy: str
    payload: dict
    result: Optional[dict] = None

    @classmethod
    def load(cls, path):
        try:
            text = path.read_text()
            data = json.loads(text)
        except Exception:
            raise Refused('Invalid request file')
        if not isinstance(data, dict):
            raise Refused('Request must be object')
        for field in ('id', 'kind', 'status', 'createdAt', 'updatedAt', 'submittedBy', 'payload'):
            if field not in data:
                raise Refused(f'Missing field: {field}')
        if not (HEX32.match(data['id']) and data['id'] == path.stem):
            raise Refused('Invalid or mismatched ID')
        if data['kind'] not in VALID_KINDS:
            raise Refused('Invalid kind')
        if data['status'] not in VALID_STATUSES:
            raise Refused('Invalid status')
        if not ISO8601.match(data['createdAt']) or not ISO8601.match(data['updatedAt']):
            raise Refused('Invalid timestamp')
        if not isinstance(data['payload'], dict):
            raise Refused('Payload must be object')
        return cls(**data)

    def save(self, dir_path):
        dir_path = Path(dir_path)
        if dir_path.stat().st_mode & 0o777 != 0o700:
            raise Refused('Queue directory must be mode 0700')
        path = dir_path / (self.id + '.json')
        temp = dir_path / ('.' + self.id + '.tmp')
        text = json.dumps(asdict(self), separators=(',', ':'))
        temp.write_text(text)
        temp.chmod(0o600)
        os.replace(temp, path)

    def with_status(self, status, result=None):
        data = asdict(self)
        data['status'] = status
        data['updatedAt'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        if result is not None:
            data['result'] = result
        return Request(**data)


def scan_queue(dir_path):
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return []
    reqs = []
    for p in dir_path.glob('*.json'):
        if p.name.startswith('.'):
            continue
        try:
            reqs.append(Request.load(p))
        except Refused:
            pass
    reqs.sort(key=lambda r: r.createdAt, reverse=True)
    return reqs


def lock_queue(dir_path, timeout=5.0):
    """Advisory lock on queue directory. Returns file descriptor or None."""
    lock_path = Path(dir_path) / '.lock'
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def unlock_queue(fd):
    if fd is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)