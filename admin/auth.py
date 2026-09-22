"""Opaque in-memory application sessions; ingress Basic is not application login."""
import hashlib
import hmac
import re
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError

from passlib.hash import apr_md5_crypt, bcrypt


IDLE_TTL = 30 * 60
ABSOLUTE_TTL = 8 * 60 * 60
MAX_SESSIONS = 1024
LOGIN_WINDOW = 60
LOGIN_FAILURE_LIMIT = 5
LOGIN_GLOBAL_LIMIT = 100
MAX_LOGIN_CLIENTS = 1024


class LoginLimiter:
    """Bound failed + in-flight attempts; never trust forwarded client headers."""
    def __init__(self):
        self.lock = threading.Lock()
        self.records = {}

    def reserve(self, client):
        now = time.monotonic()
        with self.lock:
            self.records = {key: {ticket: at for ticket, at in attempts.items()
                                  if now - at < LOGIN_WINDOW}
                            for key, attempts in self.records.items()}
            self.records = {key: attempts for key, attempts in self.records.items() if attempts}
            attempts = self.records.get(client, {})
            if (len(attempts) >= LOGIN_FAILURE_LIMIT or
                    sum(map(len, self.records.values())) >= LOGIN_GLOBAL_LIMIT or
                    client not in self.records and len(self.records) >= MAX_LOGIN_CLIENTS):
                return None
            ticket = secrets.token_hex(16)
            attempts[ticket] = now
            self.records[client] = attempts
            return ticket

    def succeeded(self, client, ticket):
        with self.lock:
            attempts = self.records.get(client, {})
            attempts.pop(ticket, None)
            if not attempts:
                self.records.pop(client, None)



class Sessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.records = {}
        self.cookie_name = '__Host-openconcho_session'
        self.secure = True

    def token_from_headers(self, headers):
        try:
            raw = headers.get('Cookie', '')
            if len(raw) > 4096:
                return None
            cookie = SimpleCookie(raw)
            value = cookie[self.cookie_name].value
            return value if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else None
        except (CookieError, KeyError):
            return None

    def create(self, username):
        token = secrets.token_urlsafe(32)
        now = time.monotonic()
        record = {'username': username, 'csrf': secrets.token_urlsafe(32),
                  'created': now, 'last_seen': now}

        with self.lock:
            self.records = {key: value for key, value in self.records.items()
                            if self.active(value, now)}
            if len(self.records) >= MAX_SESSIONS:
                raise ValueError('Session capacity exceeded')
            self.records[hashlib.sha256(token.encode()).hexdigest()] = record
        return token, record

    def get(self, headers):
        token = self.token_from_headers(headers)
        with self.lock:
            key = hashlib.sha256(token.encode()).hexdigest() if token else None
            record = self.records.get(key)
            now = time.monotonic()
            if record and self.active(record, now):
                record['last_seen'] = now
                return record
            self.records.pop(key, None)
            return None

    @staticmethod
    def active(record, now):
        return now - record['created'] < ABSOLUTE_TTL and now - record['last_seen'] < IDLE_TTL

    def revoke(self, headers):
        token = self.token_from_headers(headers)
        if token:
            with self.lock:
                self.records.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def cookie(self, token):
        return (f'{self.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Secure; '
                f'Max-Age={ABSOLUTE_TTL if token else 0}')


def verify_login(body, users):
    if not isinstance(body, dict) or set(body) != {'username', 'password'}:
        return False
    username, password = body['username'], body['password']
    if (not isinstance(username, str) or not isinstance(password, str) or
            not 1 <= len(username) <= 128 or not 1 <= len(password.encode()) <= 1024):
        return False
    try:
        entries = [line.split(':', 1) for line in users.splitlines() if line and not line.startswith('#')]
        names = [entry[0] for entry in entries]
        if len(names) != len(set(names)) or any(len(entry) != 2 for entry in entries):
            return False
        for name, hashed in entries:
            if hmac.compare_digest(username.encode(), name.encode()):
                verifier = apr_md5_crypt if hashed.startswith('$apr1$') else bcrypt
                return verifier.verify(password, hashed)
    except (ValueError, TypeError):
        return False
    return False
