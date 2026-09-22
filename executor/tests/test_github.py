import asyncio
import base64
import hashlib
import json
import pytest


def test_cas_write_uses_sha_then_reads_back_exact_blob():
    from executor.github import GitHubMCP
    session = Session()
    bridge = GitHubMCP(session)
    original = blob_sha(session.text)
    commit = asyncio.run(bridge.write('infrastructure/honcho/config.yaml', original,
                                      'changed: true\n', 'c' * 32))
    assert (commit, session.calls[0][1]['sha'], session.calls[0][0]) == (
        'b' * 40, original, 'create_or_update_file')


@pytest.mark.parametrize('path', ['../../etc/passwd', 'infrastructure/honcho/secrets.yaml', ''])
def test_unapproved_read_and_write_paths_are_blocked(path):
    from executor.github import GitHubMCP, Refused
    bridge = GitHubMCP(Session())
    with pytest.raises(Refused):
        asyncio.run(bridge.read(path))
    with pytest.raises(Refused):
        asyncio.run(bridge.write(path, 'a' * 40, 'text', 'c' * 32))
from types import SimpleNamespace


def blob_sha(text):
    raw = text.encode()
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class Session:
    def __init__(self, text='kind: ConfigMap\n'):
        self.text = text
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        sha = blob_sha(self.text)
        if name == 'get_file_contents':
            content = [
                {'type': 'text', 'text': f'successfully downloaded text file (SHA: {sha})'},
                {'type': 'resource', 'resource': {
                    'uri': 'repo://comvl-cyber/k3s/sha/' + 'a' * 40 + '/contents/' + arguments['path'],
                    'text': self.text}},
            ]
        else:
            assert arguments['sha'] == sha
            self.text = base64.b64decode(arguments['content']).decode()
            content = [{'type': 'text', 'text': json.dumps({'commit': {'sha': 'b' * 40},
                                                         'content': {'sha': blob_sha(self.text)}})}]
        return SimpleNamespace(model_dump=lambda **kw: {'is_error': False, 'content': content})


def test_mcp_read_verifies_resource_blob_and_fixed_repository():
    from executor.github import GitHubMCP
    session = Session()
    result = asyncio.run(GitHubMCP(session).read('infrastructure/honcho/config.yaml'))
    assert (result.text, result.sha, result.commit, session.calls) == (
        session.text, blob_sha(session.text), 'a' * 40,
        [('get_file_contents', {'owner': 'comvl-cyber', 'repo': 'k3s',
          'path': 'infrastructure/honcho/config.yaml', 'ref': 'refs/heads/main'})])
