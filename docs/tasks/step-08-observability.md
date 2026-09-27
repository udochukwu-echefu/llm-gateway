# Step 8: Metrics, tracing and an audit log

- **Branch:** `feat/step-8-observability` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis; the observability stack is optional)

## Goal

Everything so far was verified by hand: reading logs, querying Postgres, curling
endpoints. An operator can't run a company gateway that way. After this step:

1. **Metrics** show at a glance how the gateway is doing: traffic, errors, latency,
   gateway overhead, tokens, spend rate, breaker states, limit rejections, queue health.
2. **Traces** show where the time went in a single request (auth, limits, each provider
   attempt), and every log line carries the trace ID.
3. An **audit log** records who changed what (keys, limits, budgets), and tampering
   with it can be detected.
4. A local **Prometheus + Grafana + Jaeger** stack, with a ready-made dashboard and
   alert rules.

## Decisions already made (binding; object in your report if you disagree)

### 1. Metrics (Prometheus)

- Use `prometheus-client`. Serve `/metrics` on a **separate port**
  (`GATEWAY_METRICS__PORT`, default 9464), bound to `127.0.0.1` by default
  (`GATEWAY_METRICS__HOST`). It must **not** be on the public API port: metrics reveal
  business information such as traffic and spend. Explain this in the threat model.
- Use a registry that's injected (not the global default), so tests are isolated.
- **Cardinality rule:** labels only take values from small, bounded sets (route,
  provider, catalogued model, status class, outcome, reason). **Never** team ID, key ID,
  request ID, user or IP. Each unique label value creates a separate time series, and
  unbounded labels take Prometheus down. Per-team numbers already live in Postgres.
  Explain this in the architecture doc, and **enforce it with a test** that inspects
  every registered metric's label names.
- Required metrics, all with the prefix `lgw_`:

  | Metric | Type | Labels |
  |---|---|---|
  | `requests_total` | counter | route, status_class |
  | `request_duration_seconds` | histogram | route |
  | `time_to_first_byte_seconds` | histogram | route (streams only) |
  | `gateway_overhead_seconds` | histogram | route |
  | `upstream_requests_total` | counter | provider, model, outcome |
  | `upstream_duration_seconds` | histogram | provider |
  | `tokens_total` | counter | provider, model, kind (prompt/completion/cached/reasoning) |
  | `cost_usd_total` | counter | provider, model |
  | `retries_total` | counter | provider, reason |
  | `fallbacks_total` | counter | from_provider, to_provider |
  | `circuit_state` | gauge | provider (0 closed, 1 half-open, 2 open) |
  | `rate_limited_total` | counter | kind (requests/tokens/concurrency/budget/auth_ip) |
  | `auth_failures_total` | counter | reason |
  | `usage_queue_depth` | gauge | — |
  | `usage_records_dropped_total` / `usage_records_lost_total` | counter | — |
  | `redis_errors_total` | counter | operation |
  | `inflight_requests` | gauge | route |

- **Gateway overhead** is the key performance number from the roadmap (target < 10 ms
  at p99): the total request time **minus** the time spent waiting on providers, or up
  to the first byte for streams. Explain why this is the number that matters for a
  gateway: provider latency isn't ours to fix.
- `cost_usd_total` is for monitoring trends only. Say plainly that it isn't the
  accounting record; Postgres is.

### 2. Tracing (OpenTelemetry)

- Use `opentelemetry-api`, `opentelemetry-sdk` and
  `opentelemetry-exporter-otlp-proto-http`, with **manual** spans (no auto-instrumentation
  packages), so we control exactly what gets recorded.
- The exporter is enabled only when `GATEWAY_TRACING__OTLP_ENDPOINT` is set. Otherwise
  tracing costs almost nothing. Support a sample ratio setting (default 1.0 locally).
- Spans: the server request; `authenticate`; `limits.admission`; **one client span per
  provider attempt** (with attempt number, retry/fallback flags, and status); and usage
  enqueue.
- Use the **OpenTelemetry GenAI semantic conventions** for attribute names on attempt
  spans (e.g. `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`). Check the current spec for
  the exact names, and record the URL and date in the ADR.
- **Never** put prompts, completions, API keys or the Authorization header in spans or
  span events. Test this.
- Accept an incoming W3C `traceparent`. Don't forward trace context to **external
  providers**, since our internal IDs don't belong in third-party logs. Make it a setting
  (default off) and explain it.
- Every structlog line includes `trace_id` and `span_id` when a span is active.

### 3. Logs

- Route the standard-library logging used by uvicorn and other libraries through
  structlog, so **every** line is JSON when `log_format=json` (left over from step 1). No
  plain-text lines on startup, errors or shutdown.

### 4. Audit log

- A Postgres table `audit_events`: id, occurred_at (UTC), actor, action, target_type,
  target_id, details (JSONB, **never secrets**: no key material, no hashes, no URLs with
  credentials), prev_hash, hash.
- **Every** admin CLI change writes an event in the **same transaction** as the change
  (create org/team/key, revoke key, set/clear limits, set budget). If the change fails,
  there's no event, and vice versa.
- Actor: `GATEWAY_ADMIN_ACTOR` if set, otherwise the OS user and hostname. Explain in the
  threat model that this identifies the operator but doesn't prove who it is (SSO is out
  of scope).
- **Append-only:** a database trigger rejects `UPDATE` and `DELETE` on `audit_events`.
- **Tamper-evident hash chain:** `hash = SHA-256(prev_hash + canonical JSON of the
  event)`. Concurrent writers must not fork the chain: serialise appends, e.g. with a
  Postgres advisory lock taken in the same transaction. Explain the chain with a simple
  analogy in the architecture doc.
- CLI: `gateway-admin audit list [--since DATE] [--action A]`, and
  `gateway-admin audit verify`, which recomputes the chain and reports the first broken
  link.

### 5. Local observability stack

- A compose **profile** `observability` (not started by default) with Prometheus,
  Grafana and Jaeger (OTLP), all images version-pinned.
- Prometheus scrapes the gateway's metrics port. Grafana comes **provisioned** with the
  Prometheus data source and one dashboard (`observability/grafana/dashboards/gateway.json`):
  traffic, error rate, p50/p99 latency and overhead, tokens and cost rate by model,
  breaker states, limit rejections, and usage queue health.
- Alert rules in `observability/prometheus/alerts.yml`: breaker open for over 5 minutes,
  5xx rate over 5% for 5 minutes, any usage records dropped or lost, gateway overhead
  p99 over 10 ms for 10 minutes, and Redis errors rising. CI validates them with
  `promtool check rules` (via the Prometheus Docker image).

### 6. Carried over from the step 7 review

- **Outcome labelling:** an unexpected exception during a provider attempt is currently
  recorded as `client_disconnected`. Only cancellation (`asyncio.CancelledError`) means
  the client left. Other exceptions must record a distinct outcome, e.g.
  `gateway_error`, and still re-open a half-open breaker. Add it to the outcome type and
  the migration if needed, and test both paths.
- **Retry-budget floor:** the budget starts empty and earns one retry per five first
  attempts, so low-traffic teams almost never get retries. Add a minimum allowance per
  window (`GATEWAY_RESILIENCE__RETRY_BUDGET_MIN_PER_WINDOW`, default 10), as in
  Finagle's retry budget, and explain it in ADR 0012. The storm protection still applies
  above the floor.

## Tests required

1. Every metric in the table exists with exactly the listed labels, and the
   **cardinality test** fails if any metric has a forbidden label name.
2. Metrics move correctly for: a success, a 4xx, an upstream 5xx with a retry, a fallback,
   a breaker opening, each limit rejection, an auth failure, and a queue drop.
3. Gateway overhead excludes provider wait time (a fake provider with a known delay: the
   overhead histogram must not include that delay).
4. `/metrics` isn't reachable on the API port.
5. Tracing with an in-memory exporter: the span tree and names, GenAI attributes on
   attempt spans, `traceparent` accepted, not forwarded to providers by default, and
   **no prompt, completion or key material** anywhere in spans or events.
6. Logs: `trace_id`/`span_id` present; uvicorn and stdlib log lines come out as JSON.
7. Audit (`db`): each CLI command writes exactly one event in the same transaction; a
   failed command writes none; UPDATE and DELETE are rejected by the trigger; `verify`
   passes on a clean chain and pinpoints a tampered row (simulate tampering by disabling
   the trigger as the table owner in the test); concurrent appends from several tasks
   produce one unbroken chain; no secret material in `details`.
8. The carried-over fixes: the outcome labelling paths and the retry-budget floor.
9. Before reporting, temporarily break each of these and confirm a test fails: (a) add a
   `team_id` label to a metric, (b) put the prompt into a span attribute, (c) write the
   audit event outside the change's transaction, (d) drop the advisory lock (the
   concurrent-append test must fail), (e) record `client_disconnected` for a non-cancel
   exception.

## Docs required

- **ADR 0014:** metrics design (separate port, cardinality rule, overhead metric) and
  tracing (manual spans, GenAI conventions, no external propagation).
- **ADR 0015:** the audit log (same-transaction writes, append-only trigger, hash chain,
  the limits of the actor identity).
- **`docs/architecture.md`:** a "Step 8" section in plain language: metrics vs logs vs
  traces (a car's dashboard vs its trip diary vs a GPS track of one journey), cardinality,
  percentiles (why p99 and not the average), and the hash chain.
- **Threat model:** exposing metrics, audit tampering, actor spoofing, and trace data
  leaking to providers.
- **README:** running the observability profile, where to find the dashboard, the audit
  commands, and a screenshot placeholder note. **Roadmap:** step 8 done, step 9 next.
  Update AGENTS.md commands if needed.

## Allowed new dependencies

`prometheus-client`, `opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-http`. Nothing else without justification.

## Out of scope

Sending alerts anywhere (Slack, PagerDuty), log shipping, SSO for the admin CLI, an HTTP
admin API (step 12), per-team dashboards.

## Report back with

- Final output of the four gates and the db, redis and live tests (exact AGENTS.md
  commands), plus `promtool check rules` output.
- The metric list as registered (name, type, labels).
- Whether you ran the observability profile, and what you checked in Grafana and Jaeger.
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
