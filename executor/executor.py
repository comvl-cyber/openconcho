"""Executor: processes queued requests via GitHub MCP + GitOps."""
import asyncio
import yaml
import json
from datetime import datetime, timezone
from executor.config import switch_model, upsert_provider, add_model, PROVIDER_PRESETS
from executor.github import GitHubMCP
from executor.queue import Request


class Refused(Exception):
    """Safe operator-facing refusal."""
    pass


async def _get_live_config(github, path):
    """Read live config and return (revision, yaml_text)."""
    blob = await github.read(path)
    return blob.commit, blob.text


async def _write_config(github, path, expected_commit, new_yaml, request_id):
    """Write new config via CAS and return new commit."""
    return await github.write(path, expected_commit, new_yaml, request_id)


def _validate_model_switch_payload(payload):
    required = ('provider', 'model', 'revision', 'testedRevision', 'testedAt', 'proofExpiresAt', 'validation')
    for k in required:
        if k not in payload:
            raise Refused(f'Missing payload field: {k}')
    if not payload['validation'].get('passed'):
        raise Refused('Validation not passed')
    if payload['revision'] != payload['testedRevision']:
        raise Refused('Revision mismatch in payload')


def _validate_provider_upsert_payload(payload):
    required = ('id', 'preset', 'name', 'url', 'credentialRef')
    for k in required:
        if k not in payload:
            raise Refused(f'Missing payload field: {k}')
    if payload['id'] != payload['preset']:
        raise Refused('ID must equal preset')


def _validate_model_add_payload(payload):
    required = ('provider', 'model')
    for k in required:
        if k not in payload:
            raise Refused(f'Missing payload field: {k}')


async def process_request(req, github, get_revision_fn, flux_reconcile_fn):
    """
    Process a single request. Returns updated Request with new status and optional result.
    get_revision_fn(path) -> (k8s_revision, yaml_text) for live config validation
    flux_reconcile_fn() -> None  (triggers Flux reconcile + rollout)
    """
    # Move to running
    running = req.with_status('running')

    try:
        if req.kind == 'model-switch':
            return await _process_model_switch(running, github, get_revision_fn, flux_reconcile_fn)
        elif req.kind == 'provider-upsert':
            return await _process_provider_upsert(running, github, get_revision_fn, flux_reconcile_fn)
        elif req.kind == 'model-add':
            return await _process_model_add(running, github, get_revision_fn, flux_reconcile_fn)
        else:
            raise Refused('Unknown request kind')
    except Refused as e:
        return running.with_status('rejected', {'message': str(e)})
    except Exception as e:
        return running.with_status('failed', {'message': f'Internal error: {type(e).__name__}'})


async def _process_model_switch(req, github, get_revision_fn, flux_reconcile_fn):
    payload = req.payload
    _validate_model_switch_payload(payload)

    provider = payload['provider']
    model = payload['model']
    tested_revision = payload['testedRevision']
    proof_expires = payload['proofExpiresAt']

    # Get live config revision from K8s (for validation)
    live_k8s_revision, live_yaml = await get_revision_fn('infrastructure/honcho/config.yaml')

    # Revalidate: current K8s revision must match testedRevision
    if live_k8s_revision != tested_revision:
        raise Refused(f'ConfigMap revision changed: expected {tested_revision}, got {live_k8s_revision}')

    # Revalidate: proof must not be expired
    proof_exp = datetime.fromisoformat(proof_expires.replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > proof_exp:
        raise Refused('Proof expired')

    # Get current model/provider for rollback annotations
    live_data = yaml.safe_load(live_yaml)['data']
    current_model = live_data.get('DERIVER_MODEL_CONFIG__MODEL', 'unknown')
    current_provider = 'unknown'
    for p, preset in PROVIDER_PRESETS.items():
        if preset['url'] == live_data.get('DERIVER_MODEL_CONFIG__OVERRIDES__BASE_URL', ''):
            current_provider = p
            break

    # Transform config
    new_yaml = switch_model(live_yaml, provider, model, req.id, current_model, current_provider)

    # Get Git blob SHA for CAS write
    blob = await github.read('infrastructure/honcho/config.yaml')

    # Write via CAS using Git blob SHA
    new_commit = await _write_config(github, 'infrastructure/honcho/config.yaml',
                                      blob.sha, new_yaml, req.id)

    # Trigger Flux reconcile + rollout
    await flux_reconcile_fn()

    # Verify applied (optional: could re-read ConfigMap)
    return req.with_status('applied', {'message': 'Model switched', 'revision': new_commit})


async def _process_provider_upsert(req, github, get_revision_fn, flux_reconcile_fn):
    payload = req.payload
    _validate_provider_upsert_payload(payload)

    # Validate against presets
    preset_id = payload['preset']
    if preset_id not in PROVIDER_PRESETS:
        raise Refused('Unknown provider preset')
    preset = PROVIDER_PRESETS[preset_id]
    if payload['url'] != preset['url']:
        raise Refused('URL does not match preset')
    if payload['credentialRef'] != preset['credential_ref']:
        raise Refused('CredentialRef does not match preset')

    # Read existing providers.yaml from K8s (for validation)
    live_k8s_revision, live_yaml = await get_revision_fn('infrastructure/honcho/providers.yaml')
    try:
        providers_data = yaml.safe_load(live_yaml) or {}
    except yaml.YAMLError:
        providers_data = {}
    providers = providers_data.get('providers', [])

    # Upsert: remove existing with same id, add new
    providers = [p for p in providers if p.get('id') != preset_id]
    new_entry = upsert_provider(preset_id, payload['name'], payload['url'], payload['credentialRef'])
    providers.append(new_entry)

    new_yaml = yaml.dump({'providers': providers}, sort_keys=False)

    # Get Git blob SHA for CAS write
    blob = await github.read('infrastructure/honcho/providers.yaml')

    # Write via CAS using Git blob SHA
    new_commit = await _write_config(github, 'infrastructure/honcho/providers.yaml',
                                      blob.sha, new_yaml, req.id)

    # Trigger Flux reconcile
    await flux_reconcile_fn()

    return req.with_status('applied', {'message': 'Provider upserted', 'revision': new_commit})


async def _process_model_add(req, github, get_revision_fn, flux_reconcile_fn):
    payload = req.payload
    _validate_model_add_payload(payload)

    provider = payload['provider']
    model = payload['model']

    # Read providers.yaml from K8s (for validation)
    live_k8s_revision, live_yaml = await get_revision_fn('infrastructure/honcho/providers.yaml')
    try:
        providers_data = yaml.safe_load(live_yaml) or {}
    except yaml.YAMLError:
        providers_data = {}

    # Verify model in catalog (would need catalog fetch - simplified here)
    # In real impl, fetch fresh catalog from provider
    library = providers_data.get('library', [])
    if not any(e.get('provider') == provider and e.get('model') == model for e in library):
        library.append({'provider': provider, 'model': model})

    providers_data['library'] = library
    new_yaml = yaml.dump(providers_data, sort_keys=False)

    # Get Git blob SHA for CAS write
    blob = await github.read('infrastructure/honcho/providers.yaml')

    # Write via CAS using Git blob SHA
    new_commit = await _write_config(github, 'infrastructure/honcho/providers.yaml',
                                      blob.sha, new_yaml, req.id)

    # No Flux reconcile needed for library-only change (ConfigMap data change triggers rollout)
    # But trigger anyway for consistency
    await flux_reconcile_fn()

    return req.with_status('applied', {'message': 'Model added to library', 'revision': new_commit})