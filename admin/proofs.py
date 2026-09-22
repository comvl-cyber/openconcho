"""Bounded, expiring, session-bound single-use compatibility capabilities."""
import hashlib
import re
import secrets
import threading
import time
from datetime import datetime, timezone

PROOF_TTL = 300
MAX_PROOFS = 1024


def utc_timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Proofs:
    def __init__(self):
        self.lock = threading.Lock()
        self.records = {}

    def issue(self, provider, model, revision, session):
        now = time.monotonic()
        wall = time.time()
        token = secrets.token_urlsafe(32)
        payload = {'provider': provider, 'model': model, 'revision': revision,
                   'testedRevision': revision, 'testedAt': utc_timestamp(wall),
                   'proofExpiresAt': utc_timestamp(wall + PROOF_TTL)}
        with self.lock:
            self.records = {key: record for key, record in self.records.items()
                            if record['expires'] > now}
            if len(self.records) >= MAX_PROOFS:
                raise ValueError('Compatibility proof capacity exceeded; retry later')
            self.records[hashlib.sha256(token.encode()).digest()] = {
                'session': session, 'expires': now + PROOF_TTL, 'payload': payload}
        return {'proof': token, 'testedAt': payload['testedAt'], 'proofExpiresAt': payload['proofExpiresAt']}

    def consume(self, token, provider, model, revision, session, current_revision):
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise ValueError('Invalid or expired compatibility proof; retest required')
        key = hashlib.sha256(token.encode()).digest()
        with self.lock:
            record = self.records.get(key)
            now = time.monotonic()
            if record and record['expires'] <= now:
                self.records.pop(key, None)
                record = None
            if (not record or record['session'] is not session or
                    any(record['payload'][field] != value for field, value in
                        (('provider', provider), ('model', model), ('revision', revision))) or
                    revision != current_revision):
                raise ValueError('Invalid or expired compatibility proof; retest required')
            self.records.pop(key)
            return dict(record['payload'])
