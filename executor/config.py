"""ConfigMap transformation. No external calls, pure functions."""
import re
import yaml
from dataclasses import dataclass

SLOTS = (
    'DERIVER_MODEL_CONFIG', 'SUMMARY_MODEL_CONFIG',
    'DREAM_DEDUCTION_MODEL_CONFIG', 'DREAM_INDUCTION_MODEL_CONFIG',
    'DIALECTIC_LEVELS__minimal__MODEL_CONFIG', 'DIALECTIC_LEVELS__low__MODEL_CONFIG',
    'DIALECTIC_LEVELS__medium__MODEL_CONFIG', 'DIALECTIC_LEVELS__high__MODEL_CONFIG',
    'DIALECTIC_LEVELS__max__MODEL_CONFIG',
)

PROVIDER_PRESETS = {
    'openrouter': {'name': 'OpenRouter', 'url': 'https://openrouter.ai/api/v1', 'credential_ref': 'OPENROUTER_API_KEY'},
    'openai': {'name': 'OpenAI', 'url': 'https://api.openai.com/v1', 'credential_ref': 'OPENAI_API_KEY'},
    'deepseek': {'name': 'DeepSeek', 'url': 'https://api.deepseek.com/v1', 'credential_ref': 'DEEPSEEK_API_KEY'},
    'groq': {'name': 'Groq', 'url': 'https://api.groq.com/openai/v1', 'credential_ref': 'GROQ_API_KEY'},
    'together': {'name': 'Together', 'url': 'https://api.together.xyz/v1', 'credential_ref': 'TOGETHER_API_KEY'},
    'mistral': {'name': 'Mistral', 'url': 'https://api.mistral.ai/v1', 'credential_ref': 'MISTRAL_API_KEY'},
}


class Refused(ValueError):
    """Safe, operator-facing reason (never include external error text)."""


def _load_cm(yaml_text):
    obj = yaml.safe_load(yaml_text)
    if obj.get('kind') != 'ConfigMap' or obj.get('metadata', {}).get('name') != 'honcho-config':
        raise Refused('Invalid ConfigMap')
    return obj


def _dump_cm(obj):
    return yaml.dump(obj, sort_keys=False, width=10**9)


def switch_model(yaml_text, provider, model, request_id, prev_model, prev_provider):
    """Switch all SLOTS to new model/provider. Preserve embedding keys and all other data."""
    if provider not in PROVIDER_PRESETS:
        raise Refused('Unknown provider')
    if not re.fullmatch(r'[a-f0-9]{32}', request_id):
        raise Refused('Invalid request ID')
    preset = PROVIDER_PRESETS[provider]
    obj = _load_cm(yaml_text)
    data = obj['data']
    for slot in SLOTS:
        data[slot + '__MODEL'] = model
        data[slot + '__OVERRIDES__BASE_URL'] = preset['url']
        data[slot + '__OVERRIDES__API_KEY_ENV'] = preset['credential_ref']
    ann = obj.setdefault('metadata', {}).setdefault('annotations', {})
    ann['openconcho.io/previous-model'] = prev_model
    ann['openconcho.io/previous-provider'] = prev_provider
    ann['openconcho.io/model-change'] = request_id
    return _dump_cm(obj)


def upsert_provider(preset_id, name, url, credential_ref):
    """Validate exact preset URL and credential ref. Return dict for providers.yaml."""
    if preset_id not in PROVIDER_PRESETS:
        raise Refused('Unknown provider preset')
    preset = PROVIDER_PRESETS[preset_id]
    if url != preset['url']:
        raise Refused('Provider URL does not match preset')
    if credential_ref != preset['credential_ref']:
        raise Refused('Provider credentialRef does not match preset')
    return {'id': preset_id, 'preset': preset_id, 'name': name, 'url': url, 'credentialRef': credential_ref}


def add_model(catalog, provider, model_id):
    """Verify model exists in fresh catalog. Return library entry dict."""
    if provider not in PROVIDER_PRESETS:
        raise Refused('Unknown provider')
    if not isinstance(catalog.get('models'), list):
        raise Refused('Invalid catalog format')
    if model_id not in {m.get('id') for m in catalog['models'] if isinstance(m, dict)}:
        raise Refused('Model not in provider catalog')
    return {'provider': provider, 'model': model_id}