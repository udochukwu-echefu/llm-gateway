# LLM Gateway

One OpenAI-compatible API in front of many model providers, built for company use:
central keys, per-team limits and budgets, cost tracking, failover and audit logs.

> **Status: step 7 of 12.** Chat completions and embeddings route to Groq, DeepSeek,
> Gemini or OpenAI. Every `/v1` request requires a gateway-issued key; Redis coordinates
> team limits and budgets across replicas. Bounded retries, local circuit breakers and
> approved opt-in fallback recover from provider failures. See the
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
| `GET /readyz` | Database and Redis readiness (Redis outage keeps it ready in fail-open mode) |

`/healthz` and `/readyz` are public; `/v1/*` requires `Authorization: Bearer lgw_...`.
Missing, unknown, revoked and expired keys all receive the same 401 body. Manage keys
offline with `gateway-admin list-keys <org> [<team>]` and `gateway-admin revoke-key <key_id>`.

## Pricing and usage

Edit `catalog/models.toml` through code review: verify each model's per-million-token
standard USD prices on its provider's **official** pricing page, update `source_url`
and `checked_on` in each `[[models.periods]]` entry, set its UTC `effective_from`
date, and increment the top-level `version`. Periods must be nonempty, ordered,
and have unique dates; each request keeps the rate in force when it started.
Invalid prices, duplicate
models, or an unknown provider prevent startup. Uncatalogued models return
`404 model_not_found` before any provider call. Do not guess missing prices;
`gemini-embedding-001` is currently excluded because its official price is not listed.
`gemini-embedding-2` is catalogued at Google's paid standard **text** input rate
of $0.20 per million tokens (checked 2026-09-27); non-text media have different
prices and are not supported by this text-only embedding endpoint.
Google's OpenAI-compatible embedding response currently omits token usage, so
Gemini embedding records have `usage_missing`/NULL cost until usage is available;
this price alone cannot establish actual spend.
The reviewed DeepSeek price uses the published **peak** rate; off-peak invoices are
lower. Gemini 3.8 Flash's published rate increase on 2027-01-01 is already
entered as a second period.

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

## Team limits and budgets

`docker compose up -d` starts Postgres **and Redis**. Set `GATEWAY_REDIS_URL` explicitly;
the gateway refuses to start without it. Like the database URL it may contain a password
and is resolved by the secret store. Migrate before administering limits:

```bash
uv run gateway-admin set-limits example-org example-team --rpm 60 --tpm 120000 --max-concurrency 4
uv run gateway-admin set-budget example-org example-team 25.00 --alert-at 0.8
uv run gateway-admin show-limits example-org example-team
uv run gateway-admin clear-limits example-org example-team
```

Limit commands print an aligned table showing each value's source (override,
default or unlimited), monthly budget/spend in USD and percent, remaining requests
and tokens, and active leases. `show-limits` requires Redis; set/clear still update
Postgres when Redis is offline and display live values as `unavailable`.

NULL team values inherit global defaults. A zero (or unset) default means unlimited.
Limit updates become visible when the verified-key cache expires (30 seconds by default).
RPM checks at admission; TPM adds actual tokens only once the response ends. A finite
concurrency limit bounds the number of in-flight calls that can overshoot TPM. Monthly
USD budgets block at 100%; one `budget_alert` warning per team and month occurs at
the threshold. Unknown or missing usage and in-flight calls are not included; this
is not an exact billing ceiling.
An off-request-path reconciliation checks Postgres and the usage writer every five
minutes by default. A Redis-outage undercount heals by the next run once receipts
are durable; permanently lost receipts and unknown costs remain accounting gaps.

Authenticated responses carry `x-ratelimit-limit-requests`,
`x-ratelimit-remaining-requests`, `x-ratelimit-reset-requests` and the same three
`-tokens` headers (reset and `Retry-After` are seconds). `429 rate_limit_exceeded`
is RPM, TPM or failed-IP authentication; `429 concurrency_limit_exceeded` has
`Retry-After: 1`; `429 budget_exceeded` has type `insufficient_quota` and retries
next month. If Redis is unavailable, the default `open` mode allows requests and
logs a bounded error; `closed` returns `503 limits_unavailable`.

## Development

```bash
uv run pytest            # tests (no network: providers are mocked)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # strict type check
uv run --env-file .env pytest -m live  # opt-in smoke calls, skipped for missing keys
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run pytest -q -m redis
```

CI runs all four plus migrations, Postgres and Redis tests, then builds and smoke-tests the image.
Database tests skip locally without `GATEWAY_TEST_DATABASE_URL` and fail rather than skip
in CI. Each test session creates and drops a fresh database.
Redis tests skip locally without `GATEWAY_TEST_REDIS_URL` and fail in CI without it.

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
| `GATEWAY_REDIS_URL` | required | Redis URL, resolved via secret store; no implicit localhost fallback |
| `GATEWAY_LIMITS__DEFAULT_RPM`, `DEFAULT_TPM`, `DEFAULT_MAX_CONCURRENCY` | `0` | Global team limits (0 = unlimited) |
| `GATEWAY_LIMITS__DEFAULT_MONTHLY_BUDGET_USD` | `0` | Global USD budget (0 = unlimited) |
| `GATEWAY_LIMITS__DEFAULT_ALERT_THRESHOLD` | `0.8` | Budget warning fraction |
| `GATEWAY_LIMITS__IP_FAILURES_PER_MINUTE` | `20` | Failed authentications per client IP |
| `GATEWAY_LIMITS__LEASE_TTL_S` | `900` | Lease expiry; active requests renew periodically; set longer than any expected renewal stall |
| `GATEWAY_LIMITS__REDIS_TIMEOUT_S` | `0.05` | Redis socket timeout in seconds |
| `GATEWAY_LIMITS__BUDGET_REBUILD_TIMEOUT_S` | `0.2` | Total budget rebuild deadline (Postgres query and Redis lock wait); timeout follows fail mode |
| `GATEWAY_LIMITS__BUDGET_RECONCILE_INTERVAL_S` | `300` | Background Postgres-to-Redis budget reconciliation interval in seconds |
| `GATEWAY_LIMITS__FAIL_MODE` | `open` | `open` permits traffic if Redis fails; `closed` returns 503 |
| `GATEWAY_TRUSTED_PROXY_HOPS` | `0` | Number of trusted proxy hops from right of X-Forwarded-For; 0 trusts only socket |
| `GATEWAY_API_KEY_PEPPER` | required | Private 32+ byte HMAC pepper; rotating it invalidates all keys |
| `GATEWAY_SECRETS__BACKEND` | `env` | `env` or `file` |
| `GATEWAY_SECRETS__DIR` | unset | Required for file backend; mode 0700 directory, 0600 files |
| `GATEWAY_KEY_CACHE_TTL_S` | `30` | Per-replica verified-key cache TTL in seconds |
| `GATEWAY_KEY_CACHE_MAX_SIZE` | `10000` | Maximum cache entries (LRU) |
| `GATEWAY_USAGE_QUEUE_SIZE` | `10000` | Maximum queued records; overflow drops with an error log |
| `GATEWAY_USAGE_BATCH_SIZE` | `500` | Maximum records per insert |
| `GATEWAY_USAGE_FLUSH_INTERVAL_S` | `1` | Maximum seconds before a partial batch is inserted |
| `GATEWAY_USAGE_SHUTDOWN_TIMEOUT_S` | `10` | Maximum seconds to drain on shutdown |

In file mode, names are `api_key_pepper`, `database_url`, `redis_url`, and
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
   [ADR 0009: usage writer](docs/adr/0009-batched-usage-writer.md),
   [ADR 0010: Redis limits](docs/adr/0010-redis-limits.md),
   [ADR 0011: budgets and failure mode](docs/adr/0011-budgets-and-failure.md).
- [Security threat model](docs/security/threat-model.md)

## Resilience and approved fallback

Run `uv run alembic upgrade head` before deploying this step (migration 0004 adds
`attempt` and `fallback_from` to usage receipts). Usage reports count provider attempts;
use their shared request ID to group a client request.

To approve fallback, add `fallbacks` on the source model entry in `catalog/models.toml`,
**before** its `[[models.periods]]` price tables. For example, on the existing
`groq/openai/gpt-oss-20b` entry:

```toml
fallbacks = ["deepseek/deepseek-flash", "groq/openai/gpt-oss-120b"]
```

Every target must be catalogued with the same kind; self-references and cycles fail
startup. No fallback is enabled in the shipped catalogue. Approval permits sending
prompts to the target company: check contracts and residency before enabling it.
Only the source's direct list is tried, in order, skipping unconfigured providers,
open circuits and unsupported capabilities. Targets use their own `provider_options`.

Clients can refuse alternatives with `x-lgw-fallback: disabled`. The returned `model`
identifies what actually served the request. When any retry or fallback occurred,
`x-lgw-attempts` reports network attempts and `x-lgw-fallback-from` reports the original
model (both headers also appear for retries on the original provider and terminal errors).
An open circuit with no usable fallback returns the normal OpenAI error envelope with
HTTP 503 and code `provider_unavailable`. Exhausted calls retain their mapped provider
error; the overall deadline returns `504 upstream_timeout`. Mid-stream errors remain
terminal SSE events and never retry or switch models.

All settings below use the `GATEWAY_RESILIENCE__` prefix. Invalid settings fail startup.

| Suffix | Default | Meaning |
|---|---|---|
| `MAX_RETRIES` | `2` | Extra attempts allowed per target, subject to budget |
| `RETRY_BASE_S` | `0.25` | Initial full-jitter upper bound |
| `RETRY_CAP_S` | `2` | Maximum jitter or honored Retry-After delay |
| `RETRY_READ_TIMEOUTS` | `false` | Opt into potentially duplicate-billed read retries |
| `RETRY_BUDGET_RATIO` | `0.2` | Retries divided by first attempts, per provider/replica |
| `RETRY_WINDOW_S` | `60` | Rolling retry-credit window; no initial credit |
| `DEADLINE_S` | `60` | Total provider execution time, until first chunk for streams |
| `BREAKER_WINDOW_S` | `30` | Rolling observation window |
| `BREAKER_MIN_CALLS` | `10` | Minimum attempts before opening |
| `BREAKER_FAILURE_RATIO` | `0.5` | Failure fraction that opens the circuit |
| `BREAKER_OPEN_S` | `30` | Time before the one half-open probe |

Connect failures and selected 429/5xx statuses may retry; other 4xx never do. A
Retry-After above the cap exhausts that target immediately. Redis is not involved in
recovery policy. See [ADR 0012](docs/adr/0012-safe-retries.md) and
[ADR 0013](docs/adr/0013-breakers-and-approved-fallbacks.md) for billing limits and semantics.
