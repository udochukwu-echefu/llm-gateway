# LLM Gateway

One OpenAI-compatible API in front of many model providers, built for company use:
central keys, per-team limits and budgets, cost tracking, failover and audit logs.

> **Status: step 5 of 12.** Chat completions and embeddings route to Groq, DeepSeek,
> Gemini or OpenAI. Every `/v1` request requires a gateway-issued key. Rate limits and
> budgets are not yet implemented; do not expose this service publicly. See the
> [roadmap](docs/roadmap.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Docker Desktop. Examples below use
**local-only fake credentials**; replace the pepper and provider key privately.

```bash
uv sync
docker compose up -d
cp .env.example .env        # set a unique 32+ byte pepper and at least one provider key
set -a; . ./.env; set +a     # CLI reads environment variables; keep .env private
uv run alembic upgrade head
uv run gateway-admin create-org example-org
uv run gateway-admin create-team example-org example-team
uv run gateway-admin create-key example-org example-team example-client
# Save the printed key: it is shown only once; set it in your shell as GATEWAY_CLIENT_KEY.
uv run uvicorn llm_gateway.main:create_app --factory --no-access-log --reload
```

Call it like OpenAI:

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $GATEWAY_CLIENT_KEY" \
  -d '{"model": "groq/openai/gpt-oss-20b", "stream": true,
       "messages": [{"role": "user", "content": "Say hi in five words"}]}'
```

Or point any OpenAI SDK at it:

```python
from openai import OpenAI

import os

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key=os.environ["GATEWAY_CLIENT_KEY"])
```

Provider-only options go in `provider_options`, and only the serving provider's are sent:

```python
client.chat.completions.create(
    model="groq/openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "hi"}],
    extra_body={"provider_options": {"groq": {"include_reasoning": False}}},
)
```

## Endpoints

| Endpoint | Notes |
|---|---|
| `POST /v1/chat/completions` | Streaming and non-streaming; optional features depend on provider and model |
| `POST /v1/embeddings` | Only catalogued embedding models; currently `openai/text-embedding-3-small` |
| `GET /v1/models` | Authenticated OpenAI-compatible list of reviewed models for configured providers |
| `GET /healthz` | Liveness |
| `GET /readyz` | Database readiness (503 when unavailable) |

`/healthz` and `/readyz` are public; `/v1/*` requires `Authorization: Bearer lgw_...`.
Missing, unknown, revoked and expired keys all receive the same 401 body. Manage keys
offline with `gateway-admin list-keys <org> [<team>]` and `gateway-admin revoke-key <key_id>`.

## Pricing and usage

Edit `catalog/models.toml` through code review: verify each model's per-million-token
standard USD prices on its provider's **official** pricing page, update `source_url`
and `checked_on`, and increment the top-level `version`. Invalid prices, duplicate
models, or an unknown provider prevent startup. Uncatalogued models return
`404 model_not_found` before any provider call. Do not guess missing prices;
`gemini-embedding-001` is currently excluded because its official price is not listed.
The reviewed DeepSeek price uses the published **peak** rate; off-peak invoices are
lower. Gemini 3.8 Flash's reviewed promotional rate expires on 2026-12-31.

Usage records contain identity, token counts, USD cost and outcome, not request or
response content. They are batched asynchronously into Postgres. A full queue or an
abrupt process kill can lose records; missing cost is NULL, not zero. Reconcile with
provider invoices rather than using these estimates as an invoice ledger.

```bash
uv run gateway-admin usage example-org --team example-team --since 2026-09-01 --until 2026-09-30 --group-by model
# Other grouping: team (default), key, day
```

The CLI aggregates in SQL and prints request count, token sums, total USD and
counts of `usage_missing` and `stream_incomplete` so unpriced calls stay visible.

## Development

```bash
uv run pytest            # tests (no network: providers are mocked)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # strict type check
uv run --env-file .env pytest -m live  # opt-in smoke calls, skipped for missing keys
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
```

CI runs all four plus migrations and Postgres tests, then builds and smoke-tests the image.
Database tests skip locally without `GATEWAY_TEST_DATABASE_URL` and fail rather than skip
in CI. Each test session creates and drops a fresh database.

Live tests read `GATEWAY_PROVIDERS__<PROVIDER>__API_KEY` from the process environment
(load `.env` explicitly with `uv run --env-file .env`), and optional matching `BASE_URL`
overrides. They run one chat and one stream with priced records per configured provider;
OpenAI embeddings run when configured. Gemini's embedding smoke test is skipped until
its model has an official published price. The default suite deselects live tests and
blocks real provider HTTP requests.

Override smoke-test model IDs without editing code:

```bash
GATEWAY_LIVE_GROQ_CHAT_MODEL=openai/gpt-oss-20b uv run --env-file .env pytest -m live
GATEWAY_LIVE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small uv run --env-file .env pytest -m live
```

Every provider accepts `GATEWAY_LIVE_<PROVIDER>_CHAT_MODEL` and
`GATEWAY_LIVE_<PROVIDER>_EMBEDDING_MODEL` (`GROQ`, `DEEPSEEK`, `GEMINI`, `OPENAI`).
Use provider-native model IDs, including any internal slashes; tests add the gateway
provider prefix. Unset or empty overrides retain the defaults below.

| Provider | Default live chat model | Default live embedding model |
|---|---|---|
| Groq | `openai/gpt-oss-20b` | None (unsupported endpoint) |
| DeepSeek | `deepseek-flash` | None (unsupported endpoint) |
| Gemini | `gemini-3.8-flash` | `gemini-embedding-001` (skipped: no verified price) |
| OpenAI | `gpt-4.1-nano` | `text-embedding-3-small` |

Groq's default replaces retired `llama-3.1-8b-instant`, exercises first-slash routing,
and uses its reasoning-capable GPT-OSS adapter path. These variables configure tests only;
they do not create gateway aliases or enable unsupported endpoints. Model-selection unit
tests run offline in the default suite; only provider smoke calls carry the `live` marker.

## Configuration

All settings are environment variables prefixed `GATEWAY_` (see `src/llm_gateway/config.py`).

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_PROVIDERS__GROQ__API_KEY` | unset | Enable Groq |
| `GATEWAY_PROVIDERS__DEEPSEEK__API_KEY` | unset | Enable DeepSeek |
| `GATEWAY_PROVIDERS__GEMINI__API_KEY` | unset | Enable Gemini's OpenAI-compatible endpoint |
| `GATEWAY_PROVIDERS__OPENAI__API_KEY` | unset | Enable OpenAI |
| `GATEWAY_PROVIDERS__<PROVIDER>__BASE_URL` | provider default | Optional HTTP(S) endpoint override |
| `GATEWAY_READ_TIMEOUT_S` | 60 | Longest silence allowed between chunks |
| `GATEWAY_MAX_REQUEST_BYTES` | 2 MiB | Larger bodies are rejected with 413 |
| `GATEWAY_LOG_FORMAT` | `json` | `json` or `console` |
| `GATEWAY_DATABASE_URL` | required | Postgres asyncpg URL (contains a password) |
| `GATEWAY_API_KEY_PEPPER` | required | Private 32+ byte HMAC pepper; rotating it invalidates all keys |
| `GATEWAY_SECRETS__BACKEND` | `env` | `env` or `file` |
| `GATEWAY_SECRETS__DIR` | unset | Required for file backend; mode 0700 directory, 0600 files |
| `GATEWAY_KEY_CACHE_TTL_S` | `30` | Per-replica verified-key cache TTL in seconds |
| `GATEWAY_KEY_CACHE_MAX_SIZE` | `10000` | Maximum cache entries (LRU) |
| `GATEWAY_USAGE_QUEUE_SIZE` | `10000` | Maximum queued records; overflow drops with an error log |
| `GATEWAY_USAGE_BATCH_SIZE` | `500` | Maximum records per insert |
| `GATEWAY_USAGE_FLUSH_INTERVAL_S` | `1` | Maximum seconds before a partial batch is inserted |
| `GATEWAY_USAGE_SHUTDOWN_TIMEOUT_S` | `10` | Maximum seconds to drain on shutdown |

In file mode, names are `api_key_pepper`, `database_url`, and
`providers__<provider>__api_key`; one trailing newline is removed. Kubernetes' atomic
`..data` symlinks work when their targets stay inside the secret directory. Kubernetes
deployments must set `defaultMode: 0400` (and `fsGroup` if needed for access); the
resolved files must remain unreadable by group and others. The default `0644` mode is
refused. Environment mode
keeps `GATEWAY_PROVIDERS__*__API_KEY` (including `.env`) working. At least one nonempty
provider key is required. Each enabled provider has its own connection pool;
timeout and pool-size settings are global. The old `GATEWAY_UPSTREAM_*` settings are removed.

Use `<provider>/<model>` in every request. Only the first slash is split:
`groq/openai/gpt-oss-120b` routes to Groq with model `openai/gpt-oss-120b`.
Unknown, unprefixed or unconfigured providers return `404 model_not_found`, listing
configured providers. Responses and stream chunks prefix the provider's returned model ID.
Configured but uncatalogued models also return `404 model_not_found`.

Unsupported parameters return `400 unsupported_parameter` before a provider call.
Developer instructions become system instructions on DeepSeek and Gemini. DeepSeek's
token limit is translated to `max_tokens` (supplying both limits is rejected).
Groq's separate `reasoning` output becomes `reasoning_content`, as on DeepSeek.
Capabilities are endpoint-level; models can have additional restrictions.

Defaults: Groq `https://api.groq.com/openai/v1`, DeepSeek `https://api.deepseek.com/v1`,
Gemini `https://generativelanguage.googleapis.com/v1beta/openai`, OpenAI `https://api.openai.com/v1`.
Verified documentation and conservative restrictions are recorded in each adapter's docstring.
Undocumented parameters, including Gemini's token limits, are forwarded unchanged;
only explicit documented restrictions or nonexistent endpoints are rejected locally.

## Docs

- [Architecture, in plain language](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- Decisions: [ADR 0001: OpenAI-compatible API](docs/adr/0001-openai-compatible-api.md),
  [ADR 0002: error mapping](docs/adr/0002-upstream-error-mapping.md),
  [ADR 0003: canonical schema](docs/adr/0003-canonical-schema.md),
  [ADR 0004: provider adapters](docs/adr/0004-provider-adapters.md),
  [ADR 0005: reasoning output](docs/adr/0005-canonical-reasoning.md),
  [ADR 0006: key security](docs/adr/0006-virtual-api-keys.md),
   [ADR 0007: secret store and CLI](docs/adr/0007-secret-store-and-cli.md),
   [ADR 0008: reviewed catalogue](docs/adr/0008-reviewed-model-catalogue.md),
   [ADR 0009: usage writer](docs/adr/0009-batched-usage-writer.md).
- [Security threat model](docs/security/threat-model.md)
