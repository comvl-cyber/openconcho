# OpenConcho Executor

Deterministic host-side daemon that processes UI model/provider requests via GitHub MCP and GitOps — **without any GitHub credentials in the admin pod**.

## Architecture

```
┌─────────────────┐     Queue (JSON files)      ┌──────────────────┐
│  Admin UI/API   │  ─────────────────────────►  │  Executor Daemon │
│  (k8s pod)      │   /var/lib/openconcho/      │  (host systemd)  │
│                 │   requests/                 │                  │
└─────────────────┘                             └────────┬─────────┘
                                                         │
                              ┌──────────────────────────┼──────────────────────────┐
                              ▼                          ▼                          ▼
                       ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
                       │ GitHub MCP  │            │   Flux      │            │  Kubernetes │
                       │ (api.github-│            │  GitOps     │            │  (k3s)      │
                       │  copilot.com)│            │             │            │             │
                       └─────────────┘            └─────────────┘            └─────────────┘
```

## Components

- **executor/** — Core executor package (tests in `executor/tests/`)
  - `github.py` — Strict GitHub MCP boundary (read/write with CAS, path allowlist)
  - `config.py` — ConfigMap transformations (model-switch, provider-upsert, model-add)
  - `queue.py` — Atomic request queue I/O (mode 0600 files, 0700 dir, advisory lock)
  - `executor.py` — Request processing orchestration
  - `daemon.py` — Long-running poller with systemd integration

## Request Types

| Kind | Payload | Action |
|------|---------|--------|
| `model-switch` | `{provider, model, revision, testedRevision, testedAt, proofExpiresAt, validation}` | Update all chat SLOTS in `honcho-config`, annotate previous model/provider, commit via GitHub MCP, trigger Flux reconcile + rollout |
| `provider-upsert` | `{id, preset, name, url, credentialRef}` | Validate against frozen presets, upsert in `providers.yaml`, commit, reconcile |
| `model-add` | `{provider, model}` | Verify model in fresh catalog, append to `library` in `providers.yaml`, commit |

## Security

- **No GitHub PAT/SSH in admin pod** — Only the host daemon has MCP access via Hermes Agent's configured `github` server (uses `api.githubcopilot.com/mcp/` with Copilot token)
- **Path allowlist** — Only `infrastructure/honcho/config.yaml` and `infrastructure/honcho/providers.yaml` in `comvl-cyber/k3s` (branch `main`)
- **CAS writes** — Every write uses `create_or_update_file` with expected blob SHA; remote content verified after commit
- **Request immutability** — Queue files written atomically mode 0600; executor validates schema, kind, revision, proof expiry before applying
- **Rollback metadata** — Previous model/provider recorded in ConfigMap annotations; request result includes commit SHA
- **Secrets** — Never written to Git; `API_KEY_ENV` set to provider's credential env var (e.g. `OPENROUTER_API_KEY`), parent deployment adds secretKeyRefs

## Provider Presets (Frozen)

| ID | Name | URL | Credential Env |
|----|------|-----|----------------|
| openrouter | OpenRouter | https://openrouter.ai/api/v1 | OPENROUTER_API_KEY |
| openai | OpenAI | https://api.openai.com/v1 | OPENAI_API_KEY |
| deepseek | DeepSeek | https://api.deepseek.com/v1 | DEEPSEEK_API_KEY |
| groq | Groq | https://api.groq.com/openai/v1 | GROQ_API_KEY |
| together | Together | https://api.together.xyz/v1 | TOGETHER_API_KEY |
| mistral | Mistral | https://api.mistral.ai/v1 | MISTRAL_API_KEY |

## Deployment

1. **Parent creates** `infrastructure/honcho/providers.yaml` ConfigMap with `providers.json` and `library`
2. **Parent deploys** Honcho with all approved provider env vars as optional `secretKeyRef`s
3. **Host runs** executor daemon via systemd:
   ```bash
   # Install (as root)
   cp executor/openconcho-executor.service /etc/systemd/system/
   mkdir -p -m 700 /var/lib/openconcho/requests
   systemctl daemon-reload
   systemctl enable --now openconcho-executor
   ```

## Testing

```bash
# Unit/integration tests (fake MCP boundary)
cd /root/workspaces/openconcho
/usr/local/lib/hermes-agent/venv/bin/python -m pytest executor/tests/ -q

# Read-only real MCP verification
/usr/local/lib/hermes-agent/venv/bin/python -c "
import asyncio, yaml, re, os
from pathlib import Path
from dotenv import dotenv_values
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client
async def main():
    c = yaml.safe_load(Path('/root/.hermes/config.yaml').read_text())['mcp_servers']['github']
    env = {**dotenv_values('/root/.hermes/.env'), **os.environ}
    headers = {k: re.sub(r'\$\{([A-Za-z_][A-Za-z_0-9]*)\}', lambda m: env.get(m[1]) or '', v) for k,v in c['headers'].items()}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(c['url'], http_client=http) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                r = await session.call_tool('get_file_contents', {'owner':'comvl-cyber','repo':'k3s','path':'infrastructure/honcho/config.yaml','ref':'refs/heads/main'})
                print('MCP bridge OK')
asyncio.run(main())
"
```

## Files Created

- `executor/github.py` + tests
- `executor/config.py` + tests
- `executor/queue.py` + tests
- `executor/executor.py` + tests
- `executor/daemon.py`
- `executor/openconcho-executor.service`
- This README