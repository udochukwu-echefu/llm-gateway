# ADR 0014: Private bounded metrics and manual metadata-only tracing

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Operators need aggregate health and a timing breakdown without exposing customer content,
creating unbounded Prometheus series, or attributing provider latency to gateway overhead.

## Decision

Use `prometheus-client` with a registry injected into each app. A lifespan-owned HTTP server
binds to `GATEWAY_METRICS__HOST=127.0.0.1` and `GATEWAY_METRICS__PORT=9464`, never the API
router. `GATEWAY_METRICS__ENABLED=false` disables the socket for embedded/test apps; instruments
still exist. Deployment runs one worker per container; shared scrape ports and in-process
registries are not a multiprocess aggregation scheme. Metrics have the exact spec labels.
Routes are a fixed allowlist plus `other`; models come from selected catalogue entries rather
than untrusted response model strings. No identity or arbitrary exception text labels.

Histogram buckets include 1, 2.5, 5 and 10 ms around the overhead target and extend to 60 s.
Measure elapsed request duration minus all awaited provider operations. Stream overhead ends
at the first nonempty client body byte. This excludes waits for provider headers and chunks,
not client backpressure; retry backoff remains gateway time. Attempt duration covers its full
lifetime. Known tokens and costs count once per receipt before queue admission, so a dropped
receipt does not hide actual measured spend. Cost counters are monitoring trends; Postgres
is the accounting record and still subject to ADR 0009's loss limitations.

Evaluate the high-overhead alert only for routes averaging at least 1 request/s over
five minutes, matching the traffic guard to the histogram's window and route label.
After quiet periods, cold Postgres key lookups and budget rebuilds can take roughly
40 ms and dominate p99 in small samples; a 20-request burst triggered a pending alert.
The traffic guard avoids treating those sparse cold paths as sustained overhead trouble;
the 10 ms p99 threshold and ten-minute alert duration remain unchanged.

Use manual OpenTelemetry server, authenticate, limits.admission, client attempt and
usage.enqueue spans. Each app owns its provider; no global tracer provider or automatic HTTP
instrumentation. Only `GATEWAY_TRACING__OTLP_ENDPOINT` enables the OTLP/HTTP exporter (supply
the full `/v1/traces` endpoint). Sample ratio defaults to 1.0; a parent-based ratio sampler
honors incoming sampling decisions. No endpoint means a no-op tracer and no exporter thread.
Incoming W3C traceparent is extracted, but provider propagation defaults off. The explicit
`GATEWAY_TRACING__PROPAGATE_TO_PROVIDERS=true` setting exports only W3C trace context, never
baggage or client headers. Export failure is asynchronous and cannot fail a client request.

Current GenAI conventions checked **2026-09-27**:
- https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- https://github.com/open-telemetry/semantic-conventions-genai

The original spans page now directs readers to that repository. `gen_ai.system` is deprecated
in favor of `gen_ai.provider.name`. Use the latter (Gemini = `gcp.gemini`),
`gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`,
`gen_ai.usage.input_tokens`, and `gen_ai.usage.output_tokens`. Additional `lgw.attempt`,
`lgw.retry`, `lgw.fallback`, `lgw.outcome` and HTTP status describe recovery. Content attributes
and exception events/messages are deliberately absent. The in-memory exporter tests inspect
all span attributes/events for sentinel secrets and content.

## Consequences

Scrape endpoints and trace stores still reveal business metadata and need private access.
The local profile publishes UIs only on loopback; Grafana anonymous access is local convenience,
not a production authentication policy. Traces are sampled while metrics count all observed
requests. A trace from an untrusted client can influence sampling; collectors need capacity
limits at deployment. Tracing and metrics add small overhead; step 12 measures the SLO under load.
Standard-library/uvicorn records use structlog's JSON formatter; request logs carry active span
IDs. Exception details are suppressed because exception messages/locals can contain secrets.

## Alternatives considered

- Public `/metrics`: exposes usage and spend to API clients.
- Global collectors and tracer provider: couples tests and separate app lifetimes.
- Automatic instrumentation: risks exporting URLs, headers and external trace context.
- Team labels: unbounded cardinality; SQL already provides team reporting.

## Measurement amendment (2026-09-30)

Add sub-millisecond and 2–25 ms buckets around the SLO, preserving label sets.
Access logs now include unrounded overhead_ms from the same metric observation,
and key_cache hit/miss (null when no key lookup occurred). Observability supplies an idempotent request-scoped callback invoked before
the access line is emitted, preserving the active request trace.
Benchmark percentiles use exact log observations and report histogram estimates
alongside. Dashboard and alert queries use histogram_quantile without named bucket
boundaries, so their queries need no changes.
