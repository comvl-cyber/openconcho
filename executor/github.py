"""Strict GitHub MCP boundary. No tool names or repository paths from requests."""
import base64
import hashlib
import json
import re
from dataclasses import dataclass

OWNER = 'comvl-cyber'
REPO = 'k3s'
BRANCH = 'main'
CONFIG_PATH = 'infrastructure/honcho/config.yaml'
PROVIDERS_PATH = 'infrastructure/honcho/providers.yaml'
PATHS = frozenset((CONFIG_PATH, PROVIDERS_PATH))
MAX_BLOB = 1024 * 1024


class Refused(ValueError):
    """Safe, operator-facing reason (never include external error text)."""


def blob_sha(text):
    raw = text.encode('utf-8')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


@dataclass(frozen=True)
class Blob:
    text: str
    sha: str
    commit: str


class GitHubMCP:
    def __init__(self, session):
        self.session = session

    async def _call(self, name, arguments):
        try:
            result = await self.session.call_tool(name, arguments)
            obj = result.model_dump(by_alias=True, mode='json')
        except Exception:
            raise Refused('GitHub MCP operation failed') from None
        if obj.get('isError', obj.get('is_error', False)):
            raise Refused('GitHub MCP operation refused')
        return obj

    async def read(self, path):
        if path not in PATHS:
            raise Refused('Repository path is not approved')
        obj = await self._call('get_file_contents', {
            'owner': OWNER, 'repo': REPO, 'path': path, 'ref': 'refs/heads/' + BRANCH})
        resources = [c.get('resource', {}) for c in obj.get('content', []) if c.get('type') == 'resource']
        if len(resources) != 1:
            raise Refused('Expected one GitHub text resource')
        resource = resources[0]
        text = resource.get('text')
        match = re.fullmatch(r'repo://comvl-cyber/k3s/sha/([a-f0-9]{40})/contents/' + re.escape(path),
                             resource.get('uri', ''))
        if not match or not isinstance(text, str) or len(text.encode()) > MAX_BLOB:
            raise Refused('Invalid GitHub resource')
        sha = blob_sha(text)
        markers = [re.fullmatch(r'successfully downloaded text file \(SHA: ([a-f0-9]{40})\)', c.get('text', ''))
                   for c in obj.get('content', []) if c.get('type') == 'text']
        if not any(m and m[1] == sha for m in markers):
            raise Refused('GitHub blob integrity check failed')
        return Blob(text, sha, match[1])

    async def write(self, path, expected_sha, new_text, request_id):
        if path not in PATHS:
            raise Refused('Repository path is not approved')
        if len(new_text.encode('utf-8')) > MAX_BLOB:
            raise Refused('Content too large')
        if not re.fullmatch(r'[a-f0-9]{40}', expected_sha):
            raise Refused('Invalid expected SHA')
        if not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise Refused('Invalid request ID')
        obj = await self._call('create_or_update_file', {
            'owner': OWNER, 'repo': REPO, 'path': path, 'branch': BRANCH,
            'message': f'openconcho executor: {request_id}',
            'content': base64.b64encode(new_text.encode('utf-8')).decode('ascii'),
            'sha': expected_sha})
        commit_obj = [c for c in obj.get('content', []) if c.get('type') == 'text']
        if len(commit_obj) != 1:
            raise Refused('Expected commit response')
        data = json.loads(commit_obj[0].get('text', '{}'))
        commit = data.get('commit', {}).get('sha')
        content_sha = data.get('content', {}).get('sha')
        if not (commit and re.fullmatch(r'[a-f0-9]{40}', commit)
                and content_sha == blob_sha(new_text)):
            raise Refused('GitHub commit integrity check failed')
        return commit
