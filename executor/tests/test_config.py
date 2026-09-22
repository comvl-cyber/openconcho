import pytest
import yaml


@pytest.fixture
def config_yaml():
    return yaml.safe_load("""apiVersion: v1
kind: ConfigMap
metadata:
  name: honcho-config
  namespace: honcho
  annotations:
    openconcho.io/previous-model: z-ai/glm-5.3-flash
    openconcho.io/previous-provider: openrouter
    openconcho.io/model-change: deepseek-v4-flash-mcp-apply
data:
  LOG_LEVEL: INFO
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
  DREAM_DEDUCTION_MODEL_CONFIG__TRANSPORT: openai
  DREAM_DEDUCTION_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DREAM_DEDUCTION_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DREAM_DEDUCTION_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DREAM_INDUCTION_MODEL_CONFIG__TRANSPORT: openai
  DREAM_INDUCTION_MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DREAM_INDUCTION_MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DREAM_INDUCTION_MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DIALECTIC_LEVELS__minimal__MODEL_CONFIG__TRANSPORT: openai
  DIALECTIC_LEVELS__minimal__MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DIALECTIC_LEVELS__minimal__MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DIALECTIC_LEVELS__minimal__MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DIALECTIC_LEVELS__low__MODEL_CONFIG__TRANSPORT: openai
  DIALECTIC_LEVELS__low__MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DIALECTIC_LEVELS__low__MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DIALECTIC_LEVELS__low__MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DIALECTIC_LEVELS__medium__MODEL_CONFIG__TRANSPORT: openai
  DIALECTIC_LEVELS__medium__MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DIALECTIC_LEVELS__medium__MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DIALECTIC_LEVELS__medium__MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DIALECTIC_LEVELS__high__MODEL_CONFIG__TRANSPORT: openai
  DIALECTIC_LEVELS__high__MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DIALECTIC_LEVELS__high__MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DIALECTIC_LEVELS__high__MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
  DIALECTIC_LEVELS__max__MODEL_CONFIG__TRANSPORT: openai
  DIALECTIC_LEVELS__max__MODEL_CONFIG__MODEL: deepseek/deepseek-v4-flash
  DIALECTIC_LEVELS__max__MODEL_CONFIG__OVERRIDES__BASE_URL: https://openrouter.ai/api/v1
  DIALECTIC_LEVELS__max__MODEL_CONFIG__OVERRIDES__API_KEY_ENV: HONCHO_CHAT_API_KEY
""")


def test_slots_constant_matches_config_keys(config_yaml):
    from executor.config import SLOTS
    data = config_yaml['data']
    for slot in SLOTS:
        assert slot + '__MODEL' in data, f'missing {slot}__MODEL'
        assert slot + '__OVERRIDES__BASE_URL' in data, f'missing {slot}__OVERRIDES__BASE_URL'
        assert slot + '__OVERRIDES__API_KEY_ENV' in data, f'missing {slot}__OVERRIDES__API_KEY_ENV'


def test_embedding_keys_preserved_always(config_yaml):
    from executor.config import switch_model
    result = switch_model(yaml.dump(config_yaml), 'openrouter', 'deepseek/deepseek-chat', 'a' * 32, 'deepseek/deepseek-v4-flash', 'openrouter')
    data = yaml.safe_load(result)['data']
    assert data['EMBEDDING_MODEL_CONFIG__MODEL'] == 'baai/bge-m3'
    assert data['EMBEDDING_MODEL_CONFIG__OVERRIDES__BASE_URL'] == 'https://openrouter.ai/api/v1'


def test_all_slots_updated_on_model_switch(config_yaml):
    from executor.config import switch_model
    result = switch_model(yaml.dump(config_yaml), 'openrouter', 'deepseek/deepseek-chat', 'a' * 32, 'deepseek/deepseek-v4-flash', 'openrouter')
    data = yaml.safe_load(result)['data']
    from executor.config import SLOTS
    for slot in SLOTS:
        assert data[slot + '__MODEL'] == 'deepseek/deepseek-chat', f'slot {slot} not updated'
        assert data[slot + '__OVERRIDES__BASE_URL'] == 'https://openrouter.ai/api/v1'
        assert data[slot + '__OVERRIDES__API_KEY_ENV'] == 'OPENROUTER_API_KEY'
    ann = yaml.safe_load(result)['metadata']['annotations']
    assert ann['openconcho.io/previous-model'] == 'deepseek/deepseek-v4-flash'
    assert ann['openconcho.io/previous-provider'] == 'openrouter'
    assert ann['openconcho.io/model-change'] == 'a' * 32


def test_provider_presets_defined_and_urls_frozen():
    from executor.config import PROVIDER_PRESETS
    assert 'openrouter' in PROVIDER_PRESETS
    assert PROVIDER_PRESETS['openrouter']['url'] == 'https://openrouter.ai/api/v1'
    assert PROVIDER_PRESETS['openrouter']['credential_ref'] == 'OPENROUTER_API_KEY'
    # All URLs are https
    for p in PROVIDER_PRESETS.values():
        assert p['url'].startswith('https://')


def test_provider_upsert_rejects_unknown_preset():
    from executor.config import upsert_provider, Refused
    with pytest.raises(Refused):
        upsert_provider('unknown', 'Name', 'https://x.ai/api/v1', 'SOME_KEY')


def test_provider_upsert_rejects_wrong_url_for_preset():
    from executor.config import upsert_provider, Refused
    with pytest.raises(Refused):
        upsert_provider('openrouter', 'Name', 'https://wrong.url/api/v1', 'OPENROUTER_API_KEY')


def test_provider_upsert_rejects_wrong_credential_ref():
    from executor.config import upsert_provider, Refused
    with pytest.raises(Refused):
        upsert_provider('openrouter', 'Name', 'https://openrouter.ai/api/v1', 'WRONG_KEY')


def test_model_add_validates_catalog_id():
    from executor.config import add_model, Refused
    # This should fail - need mock catalog
    with pytest.raises(Refused):
        add_model({'models': [{'id': 'deepseek/deepseek-chat'}]}, 'openrouter', 'not-in-catalog')


def test_model_add_accepts_catalog_id():
    from executor.config import add_model
    library = add_model({'models': [{'id': 'deepseek/deepseek-chat'}]}, 'openrouter', 'deepseek/deepseek-chat')
    assert library == {'provider': 'openrouter', 'model': 'deepseek/deepseek-chat'}