"""Request queue persistence for model/provider management."""
import fcntl
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from proofs import Proofs


ALLOWED_PRESETS = {
    'openrouter': {'id': 'openrouter', 'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1', 'credentialRef': 'OPENROUTER_API_KEY'},
    'openai': {'id': 'openai', 'name': 'OpenAI', 'url': 'https://api.openai.com/v1', 'credentialRef': 'OPENAI_API_KEY'},
    'deepseek': {'id': 'deepseek', 'name': 'DeepSeek', 'url': 'https://api.deepseek.com/v1', 'credentialRef': 'DEEPSEEK_API_KEY'},
    'groq': {'id': 'groq', 'name': 'Groq', 'url': 'https://api.groq.com/openai/v1', 'credentialRef': 'GROQ_API_KEY'},
    'together': {'id': 'together', 'name': 'Together AI', 'url': 'https://api.together.xyz/v1', 'credentialRef': 'TOGETHER_API_KEY'},
    'mistral': {'id': 'mistral', 'name': 'Mistral AI', 'url': 'https://api.mistral.ai/v1', 'credentialRef': 'MISTRAL_API_KEY'},
}

CREDENTIAL_REFS = {v['credentialRef'] for v in ALLOWED_PRESETS.values()}


def _request_dir() -> Path:
    return Path(os.environ.get('REQUESTS_DIR', '/var/lib/openconcho/requests'))


def _models_library_path() -> Optional[Path]:
    """Path to model library from ConfigMap, not request dir."""
    path = os.environ.get('MODEL_LIBRARY_FILE')
    if path:
        p = Path(path)
        if p.exists():
            return p
    return None


def atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(0o700, exist_ok=True)
    # Unique temp name per write; no fixed .tmp suffix
    tmp = path.with_suffix(f'.tmp.{secrets.token_hex(8)}')
    try:
        with tmp.open('w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def list_requests() -> List[Dict[str, Any]]:
    req_dir = _request_dir()
    if not req_dir.exists():
        return []
    requests = []
    for file in sorted(req_dir.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        # Skip temp files and hidden files
        if file.name.startswith('.') or file.suffix != '.json':
            continue
        # Reject symlinks
        if file.is_symlink():
            continue
        try:
            requests.append(json.loads(file.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return requests


def get_request(request_id: str) -> Optional[Dict[str, Any]]:
    path = _request_dir() / f'{request_id}.json'
    if not path.exists() or path.is_symlink():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def create_request(kind: str, payload: Dict[str, Any], username: str) -> Dict[str, Any]:
    request_id = secrets.token_hex(16)
    now = datetime.now(timezone.utc).isoformat()
    request = {
        'id': request_id, 'kind': kind, 'status': 'queued',
        'createdAt': now, 'updatedAt': now, 'submittedBy': username, 'payload': payload,
    }
    atomic_write(_request_dir() / f'{request_id}.json', request)
    return request


def update_request(request_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request = get_request(request_id)
    if not request:
        return None
    request.update(updates)
    request['updatedAt'] = datetime.now(timezone.utc).isoformat()
    atomic_write(_request_dir() / f'{request_id}.json', request)
    return request


def validate_model_switch(payload: Dict[str, Any], provider: str, controller, session) -> Dict[str, Any]:
    if payload.get('kind') != 'model-switch' or not isinstance(payload.get('provider'), str) or not isinstance(payload.get('model'), str):
        raise ValueError('Invalid model-switch payload')
    if payload['provider'] != provider:
        raise ValueError('Provider mismatch')
    revision = payload.get('revision')
    if not isinstance(revision, str):
        raise ValueError('Revision required')
    proof = payload.get('proof')
    if not isinstance(proof, str):
        raise ValueError('Proof required')
    catalog = controller.catalogs.get(provider)
    if not catalog:
        raise ValueError('Provider catalog not available')
    _, catalog_data = catalog
    model_exists = any(m['id'] == payload['model'] for m in catalog_data['models'])
    if not model_exists:
        raise ValueError('Model not in provider catalog')
    current_revision = controller.snapshot()[0]
    if revision != current_revision:
        raise ValueError('Configuration revision changed; retest required')
    # Consume the single-use, session-bound proof atomically
    consumed = controller.proofs.consume(proof, provider, payload['model'], revision, session, current_revision)
    return {'provider': consumed['provider'], 'model': consumed['model'],
            'revision': consumed['revision'], 'testedRevision': consumed['testedRevision'],
            'testedAt': consumed['testedAt'], 'proofExpiresAt': consumed['proofExpiresAt'],
            'validation': {'passed': True}}


def validate_model_add(payload: Dict[str, Any], controller) -> Dict[str, Any]:
    if payload.get('kind') != 'model-add' or not isinstance(payload.get('provider'), str) or not isinstance(payload.get('model'), str):
        raise ValueError('Invalid model-add payload')
    provider = payload['provider']
    if provider not in ALLOWED_PRESETS:
        raise ValueError('Unknown provider')
    catalog = controller.catalogs.get(provider)
    if not catalog:
        raise ValueError('Provider catalog not available')
    _, catalog_data = catalog
    model = payload['model']
    if not any(m['id'] == model for m in catalog_data['models']):
        raise ValueError('Model not in provider catalog')
    return {'provider': provider, 'model': model}


def validate_provider_upsert(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get('kind') != 'provider-upsert' or not isinstance(payload.get('preset'), str):
        raise ValueError('Invalid provider-upsert payload')
    preset = payload['preset']
    if preset not in ALLOWED_PRESETS:
        raise ValueError('Unknown preset')
    allowed = ALLOWED_PRESETS[preset]
    for field in ('name', 'url', 'credentialRef'):
        if field not in payload or payload[field] != allowed[field]:
            raise ValueError(f'Provider field {field} must match preset')
    return {'id': allowed['id'], 'preset': preset, 'name': allowed['name'],
            'url': allowed['url'], 'credentialRef': allowed['credentialRef']}


def load_favorites() -> List[Dict[str, str]]:
    # Read from ConfigMap, not request dir
    path = _models_library_path()
    if not path:
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list) and all(isinstance(item, dict) and 'provider' in item and 'model' in item for item in data):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_favorites(favorites: List[Dict[str, str]]) -> None:
    path = _models_library_path()
    if path:
        atomic_write(path, favorites)