# LLM Gateway

One OpenAI-compatible API in front of many model providers, built for company use:
central keys, per-team limits and budgets, cost tracking, failover and audit logs.

> **Status: step 14 providers implemented; live validation pending.** Chat routes to Groq,
> DeepSeek, Gemini, OpenAI, Z.ai and NVIDIA-hosted Kimi; embeddings to Gemini/OpenAI.
> Every `/v1` request requires a gateway-issued key; Redis coordinates
> team limits and budgets across replicas. Bounded retries, local circuit breakers and
> approved opt-in fallback recover from provider failures. Guardrails block secrets,
> redact configured personal data and enforce tenant data residency. See the
> [roadmap](docs/roadmap.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Docker Desktop. Examples below use
**local-only fake credentials**; replace the pepper and provider key privately.

```bash
uv sync
# Compose checks this variable even when starting only database services.
export ADMIN_CONSOLE_SESSION_SECRET="$(openssl rand -base64 48)"
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
| `POST /v1/embeddings` | Catalogued text embedding models: OpenAI and Gemini |
| `GET /v1/models` | Authenticated list of permitted models and aliases for configured providers |
| `GET /healthz` | Liveness |
| `GET /readyz` | Database and Redis readiness (Redis outage keeps it ready in fail-open mode) |

`/healthz` and `/readyz` are public; `/v1/*` requires `Authorization: Bearer lgw_...`.
Missing, unknown, revoked and expired keys all receive the same 401 body. Manage keys
offline with `gateway-admin list-keys <org> [<team>]` and `gateway-admin revoke-key <key_id>`.

## Private admin API and usage dashboard

Set `GATEWAY_ADMIN_API__ENABLED=true` to start the separate admin listener at
`127.0.0.1:8081` (override with `GATEWAY_ADMIN_API__HOST` and `__PORT`). The public
port does not serve `/admin/v1`; the admin port does not serve `/v1` model calls.
Restrict this listener to trusted administrators and terminate TLS at the deployment
edge. Its OpenAPI documentation is at `http://127.0.0.1:8081/docs`.

After migrations, bootstrap the first platform key with database access:

```bash
uv run gateway-admin create-admin-key --role platform platform-operator
# Store the printed lgwa_ key privately as GATEWAY_ADMIN_KEY; it is shown once.
uv run gateway-admin create-admin-key --role org --org example-org org-operator
```

An org key can manage only its own organization. Another organization's URL returns
404. Admin and client keys are never interchangeable. Examples using a shell variable
so the key does not appear in command text:

```bash
curl http://127.0.0.1:8081/admin/v1/orgs \
  -H "authorization: Bearer $GATEWAY_ADMIN_KEY"
curl -X POST http://127.0.0.1:8081/admin/v1/orgs/example-org/teams \
  -H "authorization: Bearer $GATEWAY_ADMIN_KEY" \
  -H 'content-type: application/json' \
  -H 'idempotency-key: fake-example-team-create-1' \
  -d '{"name":"example-team-2"}'
curl 'http://127.0.0.1:8081/admin/v1/orgs/example-org/usage?group_by=team' \
  -H "authorization: Bearer $GATEWAY_ADMIN_KEY"
curl 'http://127.0.0.1:8081/admin/v1/orgs/example-org/teams/example-team/limits' \
  -H "authorization: Bearer $GATEWAY_ADMIN_KEY"
```

Create operations accept `Idempotency-Key`: repeating the same request within 24
hours returns the same resource ID. For key creation, only the first response contains
the secret; a retry omits it and sets `secret_already_returned: true`. If a tool loses
the first response, revoke that key and create a new one. A different body with the
same idempotency key returns 409.
Configuration reads are available for team `limits` and `budget`, plus org or team
`model-policy`, `guardrails`, and `residency` (add `?team=example-team` for team
policy). Each returns saved `overrides` and resolved `effective` values; budget
amounts are strings.
List responses use `data` and `next_cursor`; pass the latter as `cursor`, with
`page_size` from 1 to 500 (default 50). Budget amounts are decimal strings.

For the Grafana usage dashboard, provide `GATEWAY_READONLY_DB_PASSWORD` securely in
the migration and observability profile environments, then run
`docker compose --profile observability up -d --build`. Open the
[usage dashboard](http://127.0.0.1:3000/d/llm-gateway-usage/llm-gateway-usage).
It reads Postgres as `gateway_readonly`, which has no key-table access. The local
Grafana profile allows anonymous viewing; restrict it in production.

## Admin web console (step 13a)

The console runs Next.js 16.3.7 and Node 24.15.0. All admin API calls happen in its
server-side BFF. `GET /admin/v1/me` returns verified `key_id`, `name`, `role` and
an optional organization `{id, name}`, plus the valid residency `regions` list.
The admin key is sealed in a Secure,
httpOnly, SameSite=Strict session cookie, never in React props or browser API responses.
The gateway still enforces all permissions. Sessions expire after 8 hours absolutely
or 30 minutes idle; logout clears the cookie and a gateway 401 returns to sign-in.

Start Postgres and Redis, migrate, enable the private API, and issue a platform key
as described above. Save the printed key privately, then start the console:

```bash
cd admin-console
# Use Node 24.15.0 from .nvmrc and the committed package-lock.json.
npm ci
export ADMIN_API_URL=http://127.0.0.1:8081
export ADMIN_CONSOLE_ORIGIN=http://localhost:3100
# Generate a fresh secret in this shell without printing it or putting it in history.
export ADMIN_CONSOLE_SESSION_SECRET="$(openssl rand -base64 48)"
npm run dev -- --hostname localhost --port 3100
# Production: npm run build, then PORT=3100 HOSTNAME=localhost npm run start
```

Use [the console](http://localhost:3100/login) and paste the issued admin key.
Local Chromium allows Secure cookies on localhost; deployments must use HTTPS.
`ADMIN_CONSOLE_ORIGIN` must exactly match the browser's origin (scheme, host, port).
The local and Docker entry points validate before starting Next. Invalid URLs or a
missing/short secret stop the process before it can print Ready or serve requests. Keep `.env*` untracked;
do not use any `NEXT_PUBLIC_` setting for these values. Changing the session secret
invalidates existing sessions. The secret must be at least 32 characters and bytes.

For containers, set `ADMIN_CONSOLE_SESSION_SECRET` securely in the compose environment
and retain the existing gateway `.env` configuration (provider key, pepper and cache
secret when enabled). Run `docker compose --profile console up -d --build`.
This starts Postgres, Redis, the gateway with its private admin listener, and the console
at localhost:3100. The admin API port is not published by this profile. The public
model API is loopback port 8001. The console image is multi-stage and runs as UID 1001.
Compose requires the session-secret variable during interpolation, including when
only starting database services; export it before running any compose command.
The image build needs npm registry access for the exact lockfile and the pinned Node image;
installed local node_modules are used for offline development and checks.

13a includes organizations/teams, one-time tenant-key creation and confirmed revocation,
limits with override/default/unlimited sources, budgets and alert thresholds, UTC-month
usage with explicit unpriced calls, labelled request/token charts and a table alternative,
and cursor-paginated audit filtering/verification. Unknown costs are JSON null; unknown
token totals leave chart gaps instead of being plotted as zero.
Model policy, guardrails, residency, cache purge, admin-key management and SSO are 13b/later.
Closing/Escape, changing tabs or reloading discards a newly created tenant secret. If its
first response is lost, revoke the resulting key and issue a replacement. Money stays
as decimal strings and BigInt pico-dollars; no float accounting. Theme defaults to system
and can be changed to light/dark for the current document.

Login failures are throttled per browser-client IP: ten failures within a fixed minute
trigger 429 and Retry-After. Successful login resets that client's count. This is a
bounded in-memory throttle on **each replica**, reset by restart; counts are not shared.
Existing sessions bypass it. Clients sharing a NAT IP share the sign-in quota. Valid
gateway keys bypass the admin API's failure counter, so one abusive browser cannot
lock every administrator out through the BFF's shared IP.

Next Route Handlers do not expose the socket IP and preserve supplied X-Forwarded-For.
The Node entry points therefore overwrite an internal header from the socket using
Node 24's request-start channel before Next receives the request. Forging that header
or X-Forwarded-For has no effect by default. `ADMIN_CONSOLE_TRUSTED_PROXY_HOPS` is
validated as an integer 0–32, default **0**. With N trusted proxy hops, use the Nth
address from the right of X-Forwarded-For; invalid/missing selections fall back to the
socket. IPv4-mapped addresses are normalized.

Behind a load balancer, restrict direct console access to trusted proxies, make them
append the real peer or replace an untrusted chain, and set the exact hop count. Do not
set it on a publicly reachable origin. With default zero behind a balancer, all callers
share its socket-IP quota. Replicas should also have load-balancer abuse controls if
a distributed limit is needed. See [ADR 0024](docs/adr/0024-admin-console.md).

Validation from `admin-console/`:

```bash
npm run lint
npm run typecheck
npm test
npm run build
# After Python db and Redis suites finish (shared migration role), with local services up:
npm run test:e2e
CONSOLE_SCREENSHOTS=1 npm run test:e2e
npm run test:break
```

Playwright uses a disposable `console_e2e_<uuid>` Postgres database and Redis DB 13.
It starts the real gateway/public/admin listeners (ports 18090/18091) and the production
standalone console (3100, IPv6 loopback browser origin). It deliberately ignores `.env` and inherited gateway config,
uses a fake pepper/provider key and a provider URL at closed port 1, and never invokes a
provider. The database account must be able to create/drop its test database. Optional
`CONSOLE_TEST_DATABASE_URL` and `CONSOLE_TEST_REDIS_URL` select test services; defaults
match compose. Runtime admin keys are stored only in an ignored mode-0600 state file,
removed on shutdown. No traces, videos or full-key screenshots are retained.
Install Chromium beforehand with `./node_modules/.bin/playwright install chromium` on
an online machine; an offline sandbox must use the installed browser and packages.

Seven named e2e tests cover platform workflow, one-time keys, org isolation, CSP,
cookies/CSRF, revocation and login throttling. An automatic shared fixture scans every
observed browser response body and all headers in every test and reports the total. Exactly one
successful tenant-key creation JSON response may contain its newly issued tenant secret;
all other responses must omit it, and no response may contain an admin credential.
Break checks deliberately inject an admin key into a client component, remove the Origin
check, add a reveal control and drop httpOnly, require the designated test to fail, then
restore sources and the production build. Two gateway mutations additionally restore
the early IP failure-limit check and the string-None serialization bug. Each must fail
its designated HTTP regression test. This runner uses only fake, disposable test data.
CI runs lint, typing, unit/component tests, build and the same real-stack Chromium suite.

Screenshots contain synthetic workspaces and public IDs only:

![Sign-in](docs/images/console-login.png)
![Organizations](docs/images/console-organisations.png)
![Usage](docs/images/console-usage.png)
![API keys](docs/images/console-keys.png)
![Limits](docs/images/console-limits.png)
![Budget](docs/images/console-budget.png)
![Audit](docs/images/console-audit.png)
![Dark theme](docs/images/console-usage-dark.png)
![Tablet](docs/images/console-tablet.png)

See [ADR 0024](docs/adr/0024-admin-console.md) and the
[validation report](docs/tasks/step-13a-review-corrections.md).

## Pricing and usage

Edit `catalog/models.toml` through code review: verify each model's per-million-token
standard USD prices on its provider's **official** pricing page, update `source_url`
and `checked_on` in each `[[models.periods]]` entry, set its UTC `effective_from`
date, and increment the top-level `version`. Periods must be nonempty, ordered,
and have unique dates; each request keeps the rate in force when it started.
Invalid prices, duplicate
models, or an unknown provider prevent startup. Uncatalogued models return
`404 model_not_found` before any provider call. Do not guess missing prices;
an explicitly reviewed `unpriced = true` period can enable a trial model without
token rates. Its calls keep known usage with `unpriced`/NULL cost, not a fabricated
zero. Unpriced models are directly callable/listable but excluded from alias draws.
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
counts of `unpriced`, `usage_missing` and `stream_incomplete` so unknown costs stay visible.

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
RPM uses atomic GCRA slots with Redis time: any rolling minute admits at most
RPM + B while Redis is available and retains state. B defaults to 5% of RPM
rounded up (minimum one), or `GATEWAY_LIMITS__RPM_BURST`. Remaining requests means
slots available now; reset means seconds until the next slot. TPM remains an
approximate sliding counter and adds actual tokens only once the response ends. A finite
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

## Performance

Amended local campaign on Apple M2 Pro / Docker Desktop with a synthetic 200 ms
provider, 30-second warmups and exact per-request overhead:

- Fully generated scaling: **199 → 399 successful responses/s** from one to two
  replicas (**2.0×**), at eligible offered stages of 200/s and 400/s.
- One-replica SLO capacity: **100 offered requests/s**.
- At low traffic (10–25 req/s), exact overhead p99 is about **10–15 ms**
  (the cold-path "idle penalty"); **50–100 req/s meets the 10 ms target**.
- RPM=600, B=30: maximum rolling-60s atomic admissions **629**, bound **630**.
- Streaming, guardrail and ten-minute soak scenarios all ran at their declared
  amended rates. Idle-path tails are reported separately by key-cache hit/miss.

These are laptop measurements at discrete stages, including Docker virtualization;
capacity beyond the tested ceiling and production performance are unmeasured.
See the [full report and charts](docs/benchmarks/load-test-report.md),
[reproduction commands](loadtest/README.md), and [deployment checklist](docs/deployment.md).
The benchmark ignores .env and uses only a fake provider.

## Development

```bash
uv run pytest            # tests (no network: providers are mocked)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # strict type check
uv run --env-file .env pytest -m live  # opt-in smoke calls, skipped for missing keys
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run pytest -q -m redis
```

CI runs all four plus migrations, Postgres and Redis tests, then builds and smoke-tests the image.
Database tests skip locally without `GATEWAY_TEST_DATABASE_URL` and fail rather than skip
in CI. Each test session creates and drops a fresh database.
Redis tests skip locally without `GATEWAY_TEST_REDIS_URL` and fail in CI without it.

Live tests read `GATEWAY_PROVIDERS__<PROVIDER>__API_KEY` from the process environment
(load `.env` explicitly with `uv run --env-file .env`), and optional matching `BASE_URL`
overrides. They run one chat and one stream with usage records per configured provider
(NVIDIA is unpriced; the others are priced);
OpenAI and Gemini embeddings run when configured. The guardrail live test spies on the
outgoing transport body to prove email redaction and client restoration. The default suite deselects live tests and
blocks real provider HTTP requests.

Override smoke-test model IDs without editing code:

```bash
GATEWAY_LIVE_GROQ_CHAT_MODEL=openai/gpt-oss-20b uv run --env-file .env pytest -m live
GATEWAY_LIVE_OPENAI_EMBEDDING_MODEL=text-embedding-3-small uv run --env-file .env pytest -m live
```

Every provider accepts `GATEWAY_LIVE_<PROVIDER>_CHAT_MODEL` and
`GATEWAY_LIVE_<PROVIDER>_EMBEDDING_MODEL` (`GROQ`, `DEEPSEEK`, `GEMINI`, `OPENAI`, `ZAI`, `NVIDIA`).
Use provider-native model IDs, including any internal slashes; tests add the gateway
provider prefix. Unset or empty overrides retain the defaults below.

| Provider | Default live chat model | Default live embedding model |
|---|---|---|
| Groq | `openai/gpt-oss-20b` | None (unsupported endpoint) |
| DeepSeek | `deepseek-flash` | None (unsupported endpoint) |
| Gemini | `gemini-3.8-flash` | `gemini-embedding-2` |
| OpenAI | `gpt-4.1-nano` | `text-embedding-3-small` |
| Z.ai | `glm-5.3-flash` | None (no documented international endpoint) |
| NVIDIA | `moonshotai/kimi-k3` | None (chat-only Kimi endpoint) |

The two new providers use low reasoning effort and a 1024-token output limit in
these smoke calls. Run just them with
`uv run --env-file .env pytest -m live tests/live/test_providers.py -k 'zai or nvidia'`.
Live calls require keys/network and may consume paid tokens or trial credits.

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
| `GATEWAY_PROVIDERS__ZAI__API_KEY` | unset | Enable Z.ai international Model API (not Coding Plan) |
| `GATEWAY_PROVIDERS__NVIDIA__API_KEY` | unset | Enable NVIDIA API catalogue hosted Kimi trial |
| `GATEWAY_PROVIDERS__<PROVIDER>__BASE_URL` | provider default | Optional HTTP(S) endpoint override |
| `GATEWAY_READ_TIMEOUT_S` | 60 | Longest silence allowed between chunks |
| `GATEWAY_MAX_REQUEST_BYTES` | 2 MiB | Larger bodies are rejected with 413 |
| `GATEWAY_LOG_FORMAT` | `json` | `json` or `console` |
| `GATEWAY_DATABASE_URL` | required | Postgres asyncpg URL (contains a password) |
| `GATEWAY_REDIS_URL` | required | Redis URL, resolved via secret store; no implicit localhost fallback |
| `GATEWAY_CACHE_ENCRYPTION_KEY` | required when cache enabled | Base64-encoded 32-byte AES-256 key from secret store; never commit it |
| `GATEWAY_CACHE__ENABLED` | `true` | Turn response caching off entirely with `false` |
| `GATEWAY_CACHE__TTL_S` | `3600` | Cache lifetime in seconds, at most 604800 (7 days) |
| `GATEWAY_CACHE__MAX_ENTRY_BYTES` | `1048576` | Largest serialized answer to cache |
| `GATEWAY_ADMIN_API__ENABLED` | `false` | Enable the private admin HTTP listener |
| `GATEWAY_ADMIN_API__HOST` | `127.0.0.1` | Admin listener bind address |
| `GATEWAY_ADMIN_API__PORT` | `8081` | Admin listener port |
| `GATEWAY_READONLY_DB_PASSWORD` | unset | Deployment-supplied Grafana database password; migration leaves role without login when absent |
| `GATEWAY_LIMITS__RPM_BURST` | unset | Immediate request burst; defaults to max(1, ceil(RPM × 0.05)) |
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

In file mode, names are `api_key_pepper`, `database_url`, `redis_url`,
`cache_encryption_key`, and
`providers__<provider>__api_key`; one trailing newline is removed. Kubernetes' atomic
`..data` symlinks work when their targets stay inside the secret directory. Kubernetes
deployments must set `defaultMode: 0400` (and `fsGroup` if needed for access); the
resolved files must remain unreadable by group and others. The default `0644` mode is
refused. Environment mode
keeps `GATEWAY_PROVIDERS__*__API_KEY` (including `.env`) working. At least one nonempty
provider key is required. Each enabled provider has its own connection pool;
timeout and pool-size settings are global. The old `GATEWAY_UPSTREAM_*` settings are removed.

## Guardrails and data residency

Run `uv run alembic upgrade head` before deployment (migration 0008). Policies are stored
on organizations/teams, changed offline and audited atomically; no new dependency or
guardrail environment variable is required. Defaults are a minimum protection level:

| Detector | Default | Validation |
|---|---|---|
| `secret_api_key` | block | Known prefixes and length/charset, including gateway `lgw_` keys |
| `secret_private_key` | block | Complete matching BEGIN/END private-key block |
| `card_number` | redact | 13–19 digits and Luhn checksum |
| `iban` | redact | 15–34 characters and mod-97 checksum |
| `email` | allow | RFC-ish pattern with TLD |
| `phone` | allow | 7–15 digits; plus prefix, 10+ digits or local phone grouping; excludes date/time shapes |
| `ip_address` | allow | Valid IPv4 or IPv6 |

The strictest default/org/team action wins (`allow < redact < block`). Teams cannot
loosen organization rules or defaults. Set replaces that scope's override list; clear
removes it. Residency is organization ∩ team, with an absent policy allowing all regions.
Both policy types share the key-cache TTL (30 seconds by default).

```bash
uv run gateway-admin set-guardrails example-org --action email=redact --action card_number=block
uv run gateway-admin set-guardrails example-org --team example-team --action phone=redact
uv run gateway-admin set-residency example-org --allow-region us --allow-region eu
uv run gateway-admin show-guardrails example-org --team example-team
uv run gateway-admin clear-guardrails example-org --team example-team
uv run gateway-admin clear-residency example-org
```

Inspection runs after model/residency authorization and before RPM/cache. Typed codes
such as `[EMAIL_1]` preserve repeated references; originals are restored on the response,
including codes split across streaming chunks. Only a request-local in-memory mapping
knows the originals. Cache keys use redacted input. Cached output is restored only in memory for the
current caller using that request's mapping; stored cache values remain redacted.
New nonstreaming output is scanned and masked (`[OUTPUT_EMAIL_1]`) or blocked before
restore; stream output scanning is **detect-only**, reported at the end. Delivery holds
back only possible unfinished placeholders; detection also retains generated text in
request memory until completion/close.

| Error | Meaning |
|---|---|
| `400 guardrail_blocked` (`invalid_request_error`) | Input blocked; detector names only, no values, no provider receipt |
| `502 guardrail_blocked_output` (`upstream_error`) | Generated nonstreaming output blocked; provider usage still accounted |
| `403 model_not_allowed` | Model/region policy denied a direct model or all alias destinations |

Disallowed fallback targets are skipped, retaining the primary error/503 when none is
usable. `/v1/models` filters both models and aliases by region. `global` and `unknown`
are literal categories, not aliases for permitted US/EU processing.

### Reviewed processing regions (existing sources 2026-09-27; new providers 2026-09-30)

| Model | Region | Official documentation |
|---|---|---|
| `groq/openai/gpt-oss-20b` | `unknown` | [Groq data controls](https://console.groq.com/docs/your-data) |
| `zai/glm-5.3-flash`, `zai/glm-5.3-flashx`, `zai/glm-5.3` | `sg` | [Z.ai API DPA section 3](https://docs.z.ai/legal-agreement/privacy-policy): generally processed in Singapore |
| `nvidia/moonshotai/kimi-k3` | `global` | [NVIDIA Kimi geography](https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3) |
| `groq/openai/gpt-oss-120b` | `unknown` | [Groq data controls](https://console.groq.com/docs/your-data) |
| `deepseek/deepseek-flash` | `cn` | [DeepSeek privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html) |
| `gemini/gemini-3.8-flash` | `global` | [Gemini API terms](https://ai.google.dev/gemini-api/terms) |
| `gemini/gemini-embedding-2` | `global` | [Gemini API terms](https://ai.google.dev/gemini-api/terms) |
| `openai/gpt-4.1-nano` | `global` | [OpenAI data controls](https://platform.openai.com/docs/guides/your-data) |
| `openai/text-embedding-3-small` | `global` | [OpenAI data controls](https://platform.openai.com/docs/guides/your-data) |

Groq guarantees US retention, not US-only inference. DeepSeek states processing/storage
in PRC. Gemini allows worldwide facilities; OpenAI's default global endpoint has no
processing constraint. Regional endpoint eligibility alone is not a guarantee for this
deployment. Therefore US/EU-only policies currently deny every reviewed model. Review
contracts and actual endpoints when changing regions or base URLs; see
[ADR 0021](docs/adr/0021-redaction-restore-and-residency.md).

Metrics use `lgw_guardrail_findings_total{direction,detector,action}`; logs emit one
`guardrail_findings` event per inspected request; spans are `guardrails.input` and
`guardrails.output`; receipts add nullable `redaction_count` (input replacement occurrences).
All contain types/counts, never matched values. Pattern matching is incomplete: images,
audio, files, integer embedding tokens, names/addresses and obfuscated PII are not covered.
This is not content moderation or prompt-injection detection. Presidio is a future option.

## Response caching

Identical embeddings are cached by default. Chat completions require the request header
`x-lgw-cache: enabled`; `x-lgw-cache: disabled` always opts out. The response header
`x-lgw-cache` is `hit`, `miss`, `bypass` (including streams and Redis outages), or
`disabled`. A hit still spends one request-per-minute ticket, but no token, budget or
concurrency capacity. Streams, `n > 1`, errors, oversized answers and fallback answers
are never stored. Entries are isolated by team, encrypted in Redis and expire after the
configured TTL. Changing the reviewed catalogue version changes the cache fingerprint.

`gateway-admin cache purge <org> [--team T]` removes only that organization's or team's
entries with Redis SCAN + UNLINK and appends an audit event. Stop concurrent writers first
if strict invalidation matters; new requests may refill the cache during a purge.
`gateway-admin usage <org>` shows `cache_hits` and `saved_usd` by group. Estimated savings
use current reviewed prices; unknown provider token usage cannot be priced and leaves
`saved_usd` NULL. Monitor `lgw_cache_requests_total` and `lgw_cache_saved_usd_total` on
the private metrics socket.

Use a reviewed alias or `<provider>/<model>` in requests. For concrete IDs, only the first slash is split:
`groq/openai/gpt-oss-120b` routes to Groq with model `openai/gpt-oss-120b`.
Unknown or unconfigured provider prefixes return `404 model_not_found`, listing
configured providers. Responses and stream chunks prefix the provider's returned model ID.
Configured but uncatalogued models also return `404 model_not_found`.

Unsupported parameters return `400 unsupported_parameter` before a provider call.
Developer instructions become system instructions on DeepSeek, Gemini, Z.ai and NVIDIA. DeepSeek's
token limit is translated to `max_tokens` (supplying both limits is rejected).
Groq's separate `reasoning` output becomes `reasoning_content`, as on DeepSeek.
Capabilities are endpoint-level; models can have additional restrictions.

Defaults: Groq `https://api.groq.com/openai/v1`, DeepSeek `https://api.deepseek.com/v1`,
Gemini `https://generativelanguage.googleapis.com/v1beta/openai`, OpenAI `https://api.openai.com/v1`.
Z.ai `https://api.z.ai/api/paas/v4`, NVIDIA `https://integrate.api.nvidia.com/v1`.
Verified documentation and conservative restrictions are recorded in each adapter's docstring.
Undocumented parameters, including Gemini's token limits, are forwarded unchanged;
only explicit documented restrictions or nonexistent endpoints are rejected locally.

### Z.ai GLM and NVIDIA-hosted Kimi (step 14)

Use `zai/glm-5.3-flash`, `zai/glm-5.3-flashx`, `zai/glm-5.3` or
`nvidia/moonshotai/kimi-k3` for streaming or nonstreaming chat. NVIDIA is the host;
Moonshot makes Kimi. Only the first slash selects the provider. Key entitlements
may differ by model. Neither provider serves embeddings through these adapters.
Each keeps its own pool and breaker; optional BASE_URL overrides and existing
global connect/read/write/pool timeout settings apply. Existing aliases stay unchanged.

Z.ai uses verified USD/1M input/cache/output list rates of 0.15/0.03/0.50 (Flash),
0.37/0.075/1.25 (FlashX), 1.4/0.26/4.4 (GLM-5.3), effective 2026-09-30.
Sources and check dates are in the catalogue; cache storage is currently listed
as limited-time free, not included in the token-cost formula.

**NVIDIA trial-service warning:** the hosted endpoint is only for internal testing
and evaluation, not production. Its [trial terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)
permit deducted/purchased credits, so its catalogue price is **unpriced, not $0**.
Production needs a paid NVIDIA NIM or partner endpoint with newly reviewed prices
and geography. USD budgets cannot quantify trial credit consumption. Confidential
or sensitive input is prohibited by the trial terms; use synthetic nonsensitive
prompts. The gateway's pattern-based guardrails cannot guarantee contractual compliance.

When replaying Kimi tool/multi-turn history, return the complete assistant message,
including typed `reasoning_content` and `tool_calls`. Z.ai supports the same preserved
reasoning when `provider_options.zai.thinking.clear_thinking` is false. Other
providers still drop reasoning history. This text remains guardrail-inspected.
Both token-limit spellings pass unchanged; undocumented parameters are forwarded.
NVIDIA rejects top_p, n and both penalties plus system/assistant content arrays;
Z.ai rejects json_schema and disabled thinking on the reviewed GLM-5.3 models.
See [ADR 0026](docs/adr/0026-zai-nvidia-providers.md) for exact evidence and limitations.

Valid residency values are `us`, `eu`, `cn`, `sg`, `global`, `unknown`. Policies
store strings, so `sg` requires no migration. `GET /admin/v1/me` adds a `regions`
list sourced from the API's validation list; console editors should read that list,
not hard-code regions. No console changes are included in this branch.

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
| `RETRY_WINDOW_S` | `60` | Rolling retry-credit window |
| `RETRY_BUDGET_MIN_PER_WINDOW` | `10` | Minimum retries per provider per window; max of floor and ratio allowance |
| `DEADLINE_S` | `60` | Total provider execution time, until first chunk for streams |
| `BREAKER_WINDOW_S` | `30` | Rolling observation window |
| `BREAKER_MIN_CALLS` | `10` | Minimum attempts before opening |
| `BREAKER_FAILURE_RATIO` | `0.5` | Failure fraction that opens the circuit |
| `BREAKER_OPEN_S` | `30` | Time before the one half-open probe |

Connect failures and selected 429/5xx statuses may retry; other 4xx never do. A
Retry-After above the cap exhausts that target immediately. Redis is not involved in
recovery policy. See [ADR 0012](docs/adr/0012-safe-retries.md) and
[ADR 0013](docs/adr/0013-breakers-and-approved-fallbacks.md) for billing limits and semantics.

### Observability (step 8)

With Docker Desktop running and your existing `.env` configured (including provider keys
and a 32+ byte `GATEWAY_API_KEY_PEPPER`):

```bash
docker compose --profile observability up -d --build
```

This starts Postgres, Redis, a gateway on `127.0.0.1:8000`, and version-pinned observability
services. It migrates the local database first. The gateway metrics socket is private to
the compose network; it is **not** `/metrics` on the API port.

- [Grafana gateway dashboard](http://localhost:3000/d/llm-gateway/llm-gateway): provisioned
  Prometheus datasource and traffic, errors, p50/p99 latency/overhead, tokens, cost rate,
  circuit state, limits and queue-health panels. Local anonymous access is read-only.
- [Prometheus](http://localhost:9090): scrape targets, metric queries and five alert rules.
- [Jaeger](http://localhost:16686): choose service `llm-gateway`, then find a request trace.

Send authenticated traffic with an existing virtual key to populate provider panels.
Screenshot placeholder: add a redacted screenshot of this dashboard with representative
traffic before publishing a portfolio demo. Do not include customer identifiers or secrets.
The profile's UI and API ports bind to loopback; do not expose these local defaults publicly.
For a gateway running outside Docker, metrics default to `127.0.0.1:9464`. Configure your
Prometheus target/reachable bind address explicitly; never expose it through the public API.

Configuration: `GATEWAY_METRICS__HOST`, `GATEWAY_METRICS__PORT` (9464),
`GATEWAY_METRICS__ENABLED` (true), `GATEWAY_TRACING__OTLP_ENDPOINT` (unset disables export),
`GATEWAY_TRACING__SAMPLE_RATIO` (1.0), and `GATEWAY_TRACING__PROPAGATE_TO_PROVIDERS` (false).
Use the full OTLP HTTP endpoint ending in `/v1/traces`. Run one gateway worker per container
for private metrics; these registries are not a multiprocess aggregate. Incoming traceparent
is accepted, while outgoing propagation is an explicit data-sharing choice. Metrics contain
no tenant/key/request/IP labels. Cost counters are trends; Postgres is the accounting record.

The retry budget now permits the larger of ten retries per provider per rolling minute and
20% of first attempts. Set `GATEWAY_RESILIENCE__RETRY_BUDGET_MIN_PER_WINDOW=0` to remove the
floor. Unexpected attempt exceptions use `gateway_error`, distinct from cancellation.

Admin changes now write an append-only, hash-chained audit event in the same transaction:

```bash
GATEWAY_ADMIN_ACTOR=operator-name uv run --env-file .env gateway-admin set-limits acme team --rpm 100
uv run --env-file .env gateway-admin audit list --since 2026-09-27 --action set-limits
uv run --env-file .env gateway-admin audit verify

docker run --rm --entrypoint promtool -v "$PWD/observability/prometheus:/etc/prometheus:ro" prom/prometheus:v3.2.1 check rules /etc/prometheus/alerts.yml
```

Without `GATEWAY_ADMIN_ACTOR`, audit records use OS username and hostname. This is a claim,
not verified identity. Database owners can defeat the chain by rewriting it or deleting its
tail; externally retained trusted checkpoints are needed for stronger evidence. No secret
material, names or credential URLs are stored in audit details. Verification failures exit
nonzero and identify the first broken event ID.

## Model policies and aliases (step 9)

Apply migration 0006 with `uv run alembic upgrade head` before starting this version.
Existing organizations and teams retain access until a policy is set.

```bash
uv run gateway-admin set-models acme --allow "groq/*"
uv run gateway-admin set-models acme --team search --allow "groq/openai/gpt-oss-20b"
uv run gateway-admin show-models acme --team search
uv run gateway-admin clear-models acme --team search
```

Each `--allow` is an exact catalogued `provider/model` or `provider/*`. Every pattern must
match the current catalogue when set. Team access is organization **intersection** team:
a team cannot widen the organization policy. No org policy allows all catalogued models;
no team policy inherits. Set/clear operations are transactionally audited. Changes become
visible within `GATEWAY_KEY_CACHE_TTL_S` (default 30 seconds), independently per replica.
`show-models` prints org/team policies and effective catalogue models/aliases. Runtime
availability also requires configured providers and an active price period.

Clients may send `"model": "fast"`, `"smart"` or `"embed"`. Reviewed definitions live in
`catalog/models.toml`; `fast` currently splits Groq GPT OSS 20B and DeepSeek Flash 90/10,
`smart` targets Groq GPT OSS 120B, and `embed` targets Gemini Embedding 2. Alias names have
no slash, never equal provider names, and target only concrete models of one kind with
positive integer weights. For example:

```toml
[aliases.fast]
targets = [
  { model = "groq/openai/gpt-oss-20b", weight = 90 },
  { model = "deepseek/deepseek-flash", weight = 10 },
]
```

Forbidden, unconfigured and not-yet-priced targets cannot win a weighted draw. Remaining
weights are rescaled; the split is probabilistic, not sticky. Fallback targets must also
pass the same policy. `/v1/models` includes permitted available aliases (`owned_by=gateway`)
and concrete models. Responses retain the concrete `model` and add `x-lgw-alias` when an
alias was resolved. Retry/fallback headers retain the selected original concrete model.

| Result | Status / code |
|---|---|
| Concrete model denied, or every alias target forbidden | `403 model_not_allowed`, type `invalid_request_error`; no RPM/budget admission |
| Unknown alias | `404 model_not_found`; lists only usable aliases for this team |
| Alias permitted but no configured, currently priced targets | `404 model_not_found` |
| Open provider breaker and no permitted fallback | `503 provider_unavailable` |

Every attempt's nullable `usage_records.alias` supports trial analysis without storing
content. `lgw_upstream_requests_total{alias="fast"}` counts attempts by concrete model and
outcome; direct calls have `alias=""`. Unknown client names never become metric labels.
For cost and latency comparisons, query the durable receipts:

```sql
SELECT alias, provider, model, count(*) AS attempts,
       sum(cost_usd) AS cost_usd, avg(duration_ms) AS duration_ms
FROM usage_records
WHERE alias = 'fast'
GROUP BY alias, provider, model;
```

Receipts remain best effort; NULL cost is unknown, not free, and retries count as separate
attempts. See ADRs 0016 and 0017 for policy and routing decisions.

Access logs include unrounded `overhead_ms` and verified-key `key_cache` hit/miss
(null before a key lookup); overhead uses the same observation as Prometheus.
