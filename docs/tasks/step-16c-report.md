# Step 16c: quiet demo idle policy

Date: 2026-10-01. Base: `main` at `94914f2`. Branch: `fix/step-16c-demo-idle`.
Local implementation only: no merge, push, deployment, live configuration changes or
managed-resource commands. The owner's continuously awake ~490 MB observation and $7–9/month
estimate motivated this work; neither is a new measurement or a confirmed platform diagnosis.

## Changes and decisions

- `scripts/demo_traffic.py`: fixed monotonic deadline, default 600 seconds, configurable
  positive integer `DEMO_TRAFFIC_WINDOW_S`. Preserve the three startup requests (0.2 s
  pacing after responses), then 50–70 s jitter. Successes and HTTP failures consume the
  same window. Clamp the last sleep to the deadline and start no request at/after it.
  The window starts with the traffic child after console readiness, not during bootstrap.
  An absolute timeout also cancels a still-running request at the deadline; connection
  cleanup/gateway receipt finalization may drain afterward.
- `deploy/demo/config.py`, `supervisor.py`, `processes.py`: validate/pass the window without
  logging values, fix reconciliation/usage idle waits to 3600 s and batch size to one.
  Only traffic exit status zero is accepted; never restart it. Required server exits or
  unsuccessful traffic exits still fail the appliance. The local-only Compose profile
  accepts the same window override for exercising successful child completion in e2e.
- `src/llm_gateway/storage_connections.py`, `main.py`: demo-only NullPool closes every
  returned Postgres connection, eliminating idle socket traffic rather than merely disabling
  checkout pings. Demo Redis explicitly disables health checks/TCP keepalives **after URL
  parsing**, so URL query parameters cannot turn them back on. Production retains its
  exact pooling/pre-ping and Redis URL-option behavior.
- `tests/demo/test_workers.py`: fake-clock success/outage and slow-response deadline tests,
  plus cancellation of a request that never finishes (mock transport; no socket).
  `tests/demo/test_appliance.py`: enumerate the complete fixed `*_INTERVAL_S` environment
  inventory (both 3600, minimum 1800), override inherited short timers, verify immediate
  batch policy, tracing/telemetry off, configurable/invalid windows and child exit policy.
  `tests/demo/test_supervisor.py`: verify child environment propagation.
  `tests/test_storage_connections.py`: inspect actual pool/Redis connection policy without
  opening sockets, including hostile Redis URL timer overrides and unchanged production.
  `tests/usage/test_writer.py`: one receipt flushes without waiting for the hourly timer.
- README, architecture, roadmap and deployment runbook updated; ADR 0030 records the
  batching/pooling tradeoffs and corrects ADR 0028's router-only idle assumption.

Data flow: bounded traffic -> loopback gateway -> fake provider -> per-request Redis
settlement and queued receipt -> immediate single-record Postgres transaction -> connection
closed. At window completion the client/child close; no producer remains. Empty usage
queue waits locally; only the hourly reconciler can autonomously contact storage.
Example: default fake-clock requests start at 0, 0.2, 0.4, 60.4 … 540.4 s with 60 s jitter;
the last wait ends at 600 s and advancing the clock another hour starts no request.

## Periodic/background task audit

Intervals below distinguish actual scheduled work from request-checked time thresholds.
“No idle network” means once boot work and in-flight requests/receipts settle and no visitor
or external probe sends requests. Multiple operations within one reconciliation/flush
episode are not separate periodic jobs. Production defaults are unchanged.

| Task / source | Interval or bound | Appliance idle behavior |
|---|---|---|
| Synthetic producer (`scripts/demo_traffic.py`) | Three boot requests with 0.2 s pacing; then 50–70 s; fixed 600 s default window | Exits zero permanently. HTTP client closes; no autonomous minute traffic afterward. |
| Budget reconciler (`limits/reconcile.py`) | Startup run; production 300 s -> fixed demo **3600 s** after each run | Queries Postgres/repairs Redis hourly only. Per-team locks expire at 5 s, correction bound 4 s; those are episode bounds, not idle probes. |
| Usage writer (`usage/writer.py`) | Production 1 s / batch 500 -> fixed demo **3600 s** / batch **1** | A new receipt writes immediately; an empty queue timeout never invokes the sink. Failed batches get only three attempts, with 0.1/0.2 s delays, then are counted lost; no infinite retry task. |
| Verified tenant key cache (`tenants/cache.py`) | TTL **30 s** | Lazy expiry on `get`, DB lookup only on requests. No refresh task. Admin authentication also queries only on requests. |
| Breakers/retry budget (`resilience/breaker.py`, `configuration.py`, `retry.py`) | Breaker window/open **30 s**; retry window **60 s**; backoff base **0.25 s**, cap **2 s**, max two retries, total deadline **60 s** | Checked in memory during active requests. Half-open probes require a request; no scheduled probe. No idle network. |
| Concurrency lease heartbeat (`limits/service.py`, `usage/middleware.py`) | TTL **900 s**, renewal **300 s** (TTL/3) | Exists only while a response is active; cancellation/response finalization cancels and awaits it. No idle heartbeat. Budget lock contention retry is 0.01 s inside the request's 0.2 s rebuild bound. |
| Response cache/single-flight (`cache/service.py`, `api/caching.py`) | Redis expiry **3600 s** | Redis-side TTL; reads/writes/purge only on requests, no background refresh or scan. In-memory followers wait only for active leaders. |
| Postgres pool/pre-ping (`storage_connections.py`, `main.py`) | Production pre-ping on checkout, **not periodic**; no scheduled SQLAlchemy pool ping | Demo **NullPool**, closes on return and does not pre-ping. No idle sockets, hence no Postgres/asyncpg/TCP keepalive activity. Bootstrap engines dispose on completion. |
| asyncpg internal statement/pool timers | Statement-cache lifetime default **300 s**; asyncpg Pool inactive lifetime default **300 s**, but no asyncpg Pool is constructed here | Closed demo connections cannot run their timers. SQLAlchemy NullPool is not asyncpg Pool; no retained idle connection. |
| Redis connection/health/TCP keepalive (`storage_connections.py`) | Explicit demo health interval **0** (disabled), socket keepalive **false**, even if URL asks for 1 s/true | Redis-py health checks are command-triggered, not a free-running task; still explicitly disabled. Idle sockets send no keepalive/health probes. Reconnect/handshake metadata occurs on demand. No pub/sub worker exists. |
| `/healthz`, `/readyz` (`api/health.py`) | **No timer** | Health is local; readiness checks DB/Redis only when called. Supervisor calls readiness only at boot. An external router probe can prevent idle and is outside repository control. |
| Provider HTTP pools (`providers/pools.py`) | httpx keepalive expiry default **5 s**, max 20 retained connections | HTTP connection reuse/expiry is not a TCP heartbeat. No idle outbound HTTP requests; all demo providers are loopback fake endpoints. |
| NVIDIA queued-job polling (`providers/nvidia_polling.py`) | **0.25 s**, within an active request deadline | Fake provider never returns 202; no job poll is active in demo idle. Production request behavior unchanged. |
| Disconnect watchers/guardrail thread work (`api/disconnect.py`, `guardrails/scheduling.py`) | Watcher yields at **0 s** while request active; large scans offloaded per request | No task persists after request completion. No autonomous network work. |
| OTLP/traces (`observability/tracing.py`) | Normally SDK batch schedule default **5 s** when configured; demo endpoint fixed **null** | No exporter, BatchSpanProcessor or exporter thread exists in demo mode. |
| Metrics (`observability/server.py`) | Passive loopback HTTP listener on 19464; server's local accept polling default **0.5 s** | No push exporter/scraper. Counters/gauges are in-memory; outbound network only if someone adds a scraper outside this image. No Prometheus/Grafana/collector sidecar in appliance. |
| Gateway/admin/fake-provider HTTP servers (`main.py`, `admin/api/server.py`, `loadtest/fake_provider/app.py`) | Uvicorn local housekeeping **0.1 s**; HTTP idle connection timeout default **5 s** | Listeners/housekeeping do not initiate HTTP calls. WebSocket ping defaults apply only to an active WebSocket; no WebSocket routes here. Fake latency **200 ms**, stream **20 × 50 ms** is request-only. |
| Console server (`scripts/docker-start.mjs`, `lib/demo-role.mjs`, `lib/admin-client.ts`, `proxy.ts`) | Viewer role validation **once at boot**; fetch deadline 10 s. Session idle/absolute thresholds **30 min / 2 h** | Startup checks at most two viewer keys. Server routes/proxy fetch only on requests. Dynamic pages have no ISR/revalidation timer. No console cron/poll task or outgoing exporter. |
| Next telemetry (`deploy/demo/config.py`, Dockerfile) | Fixed **NEXT_TELEMETRY_DISABLED=1** | No telemetry submission. Incoming HTTP keepalive/Node socket expiry is connection cleanup, not an outbound probe. |
| Browser timers (`components/record-time.tsx`, `toasts.tsx`, `global-commands.tsx`) | Relative-time render **60 s**; toast **4 s**; typed-search debounce **0.2 s** | Relative-time/toast update local UI only. Search fetch requires a nonempty edited query; resource hooks fetch on mount/manual changes, not intervals. An unvisited demo has no browser. |
| Supervisor monitoring (`deploy/demo/supervisor.py`, `processes.py`, `output.py`) | Child `poll()` **0.2 s**; blocking log-reader threads | Local process status/pipe reads only, no periodic HTTP readiness check, network log shipper or child restart. Successful traffic exit does not fail the server. |
| Bootstrap dependencies/migration/seed/keys (`prepare.py`, `boot_keys.py`) | Dependency retry **0.2 s / 30 s bound**; advisory-lock retry **0.2 s / 30 s bound**; migration process **45 s**, boot helper **90 s**; HTTP readiness **0.1 s / 30 s bound** | Boot only, helpers exit and dispose DB/Redis. Keys rotate and missing history seeds on cold process boot, not cron. No supervisor persistence/volume task. |
| Local test/measurement harness only (`deploy/demo/compose.yaml`, `measure.py`, console e2e `appliance.mjs`) | Compose DB/Redis health checks **2 s**; test exited-container check **1 s**; measure readiness **0.1 s**, sample wait **65 s** | Host/test tooling, not shipped jobs or supervisor children. Managed appliance image has no Docker HEALTHCHECK, cron daemon or these data-service sidecars. |

Scope of the audit: all app/supervisor task creation, sleeps, timers, pool creation,
health/telemetry endpoints and browser timers; installed asyncpg/redis-py socket/timer
implementations; pinned Uvicorn/httpx/SDK defaults. This is a source/configuration audit,
not a packet-capture measurement or proof of the platform's idle implementation.

## Verification

Commands actually run from the root unless indicated:

```bash
uv run pytest -q tests/demo tests/test_storage_connections.py tests/usage/test_writer.py
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
docker compose up -d postgres redis
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run pytest -q -m redis
docker compose -f deploy/demo/compose.yaml --profile demo-test config --quiet
# admin-console/:
npm run format:check
npm run lint
npm run typecheck
npm test
ADMIN_API_URL=http://127.0.0.1:18091 ADMIN_CONSOLE_ORIGIN='http://[::1]:3300' ADMIN_CONSOLE_SESSION_SECRET=synthetic-build-placeholder-at-least-32-bytes NEXT_TELEMETRY_DISABLED=1 npm run build
CONSOLE_TEST_PORT=3300 CONSOLE_TEST_REDIS_URL=redis://127.0.0.1:6379/15 npm run test:e2e
CONSOLE_TEST_PORT=3300 DEMO_TRAFFIC_WINDOW_S=10 npm run test:e2e:demo
```

Final output lines/results:

- Targeted Python: `82 passed, 2 skipped in 4.86s` (including absolute in-flight cancellation).
- Ruff: `All checks passed!`; final repeat format: `445 files already formatted`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Offline Python: `1430 passed, 341 skipped, 40 deselected in 32.26s` (after final guard).
- DB: `275 passed, 11 skipped, 1525 deselected in 66.66s (0:01:06)` (final repeat).
- Redis: first combined DB/Redis invocation exceeded its **120 s total command timeout**
  after DB succeeded and Redis printed 39 progress dots. Redis alone was then rerun with
  a 300 s timeout and passed. Final sequential repeat after the in-flight guard:
  `66 passed, 1745 deselected in 55.68s` (database **15**).
- Compose configuration: exit 0.
- Console Prettier: `All matched files use Prettier code style!`; ESLint/tsc exit 0.
- Console Vitest: `Test Files 26 passed (26)` / `Tests 133 passed (133)`.
- Console build: `Compiled successfully`, all 16 static generation tasks complete;
  application routes dynamic/on-demand, exit 0.
- Normal e2e's first attempt refused an already-running gateway on 18090/18091.
  `lsof`/`ps` identified the pre-existing `tests/e2e/stack.py` parent PID 72612 (17:04:25).
  The owner explicitly authorized stopping that specific stack; `kill -TERM 72612`
  allowed its disposable database/server cleanup. The normal suite was then rerun on
  port 3300 with Redis database 15: **`28 passed (1.5m)`**, 2830 browser responses scanned,
  one permitted key-creation response, zero leaks.
- Demo e2e first run: **`6 passed (4.6m)`**, 679 browser responses scanned, no permitted
  credential responses and zero leaks. Port 3300, **10-second local traffic window**;
  the revision guard rebuilt the dirty appliance and the disposable profile was removed.
  A final review added absolute cancellation of an in-flight request at the traffic
  deadline (HTTP read timeouts alone do not bound a continuously streaming response).
  Targeted tests passed afterward; full Python/DB/Redis and rebuilt demo e2e were repeated
  before handoff so the final guard is not credited with an older image's test result.
- Final rebuilt demo e2e: **`6 passed (47.4s)`**, 679 responses, zero credential exceptions
  and zero leaks. Both viewer tours continued successfully beyond the configured 10-second
  window, exercising the expected clean traffic exit; the disposable profile/volumes were
  removed. No application source was
  changed during this final build/run. The full gate set passed; live sleeping remains
  unverified by design.

No real provider calls, paid evaluations or managed service mutations were made. Python
db/redis suites use local services; offline tests do not open provider sockets. Initial
strict-type errors while introducing pool inspection were corrected before passing gates;
Redis's untyped kwargs boundary has a specific justified Pyright suppression, not a blanket
ignore. No module grew beyond 400 lines as part of this change.

## Limitations and owner learning

The inbound-router rule does **not** prove internal fake traffic is harmless: requests
have storage consequences, and regional outbound policy matters. Distinguish an idle
local timer from one that performs I/O, and a checkout check from a periodic heartbeat.
Slow batching can hide fresh receipts; singleton batches avoid that without short idle
polling. Closing a Postgres connection is stronger than assuming the platform's TCP
keepalive settings are long enough.

Production defaults were preserved; demo-only tradeoffs are hourly budget repair and
per-transaction Postgres reconnect overhead. The autonomous hourly reconciler can still
do a network episode if the machine remains awake; this is the permitted >=30-minute
policy, not a promise of zero packets forever. Request cancellation cleanup/flush retries
can drain just after the traffic deadline. No retention, provider behavior or schema change.

**Not verified:** live suspend/stop, memory zero, actual wake behavior, regional outbound
policy, platform/external health checks, or cost reduction. The runbook gives control-plane
status/memory verification after the future authorized deploy.

**Freshness caveat:** a cold process boot shows fresh requests. A RAM-preserving resume
does not rerun a completed boot loop, rotate keys or top up history. Therefore the requested
“just now on every visitor wake” cannot honestly be guaranteed for every documented idle
mode while also stopping a boot loop permanently. No new visitor-triggered producer was
added; owner confirmation of cold-start versus resume is the next dependency.
