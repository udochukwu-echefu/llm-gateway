# Roadmap

Each step ends with tests, docs and a working gateway.

| # | Step | Status |
|---|---|---|
| 1 | Proxy to one provider with streaming, request IDs, structured logs, error mapping, CI | ✅ Done |
| 2 | Canonical OpenAI-compatible schema (chat, tools, structured output, embeddings), pass-through for provider-only fields | ✅ Done |
| 3 | Provider adapters: Groq, Gemini, DeepSeek, OpenAI | ✅ Done |
| 4 | Tenants and virtual API keys (inbound), secret store for provider keys (outbound) | ✅ Done |
| 5 | Model catalog with effective-dated prices; token and cost tracking, written to Postgres off the request path | ✅ Done |
| 6 | Rate limits (requests and tokens per minute), concurrency limits, budgets, all in Redis | ✅ Done |
| 7 | Retries, circuit breakers, provider fallback | ✅ Done |
| 8 | Metrics (Prometheus), tracing (OpenTelemetry), audit log | ✅ Done |
| 9 | Model routing and per-team model access policies | ✅ Done |
| 10 | Caching, isolated per team | ✅ Done |
| 11 | Guardrails: deterministic PII/secret detection, redaction and restore, data residency | ✅ Done |
| 12a | Private admin API and Postgres usage dashboard | ✅ Done |
| 12b | Load test report against our targets (SLOs) | ✅ Done: full amended campaign, exact timings, GCRA rolling bound and ten-minute soak |
| 13a | Admin console: sign-in, organizations/teams, keys, limits/budgets, usage and audit | ✅ Done |
| 13b | Model policy, guardrails, residency and cache purge console editors | ✅ Done |
| 14 | Z.ai GLM and NVIDIA-hosted Kimi/GLM chat; model-specific rules, queued Kimi polling, per-provider timeouts, account errors; Singapore residency and API region discovery | Implemented; reviewer live NVIDIA queue/GLM Flash evidence recorded; agent live billing checks pending. See docs/tasks/step-14-report.md |
| 15 | Console requests, analytics, settings, models/provider health, search, CSV, shared controls and complete synthetic demo coverage | Implemented on `feat/step-15-console-completeness`; review fixes: bounded screenshot history, readable metrics/CSV, selectable series and log latency; awaiting review |
| 16 | Public viewer demo, server-side Explore sign-in, read-only console, fake-only portable appliance and InstaCloud deployment runbook | Approved; friendly visitor identities, wrapping sidebar names and revision-checked appliance tests added; local appliance targets met, lazy wake top-up and in-memory boot keys; live on InstaCloud (owner deployment, 2026-10-01) |

Step 16b addresses the first deployment: standard-base64 cache keys, redacted child logs,
committed-code staging and the tested owner deployment runbook.

Step 16c bounds boot traffic to ten minutes (configurable), permits its successful exit,
uses hourly demo-only idle timers and prevents idle storage keepalives. Implementation is
local on `fix/step-16c-demo-idle`; not merged/deployed or live sleep-verified.
See [the periodic-task audit and gates](tasks/step-16c-report.md).

The console profile-menu follow-up is isolated on `feat/console-profile-menu` for
independent review. It reuses public demo session sign-in for the two read-only scopes,
adds account navigation and shared Appearance controls, and does not belong to the
already-approved logging/design deployment.

Steps 1–16 are merged. The console includes policy editors, cache purge, Overview
and helpful empty states; local demos use an opt-in synthetic seeder.
Completed measurement does not mean every SLO passed.
See the [report](benchmarks/load-test-report.md) for measured capacity, saturation,
scaling, guardrails, streaming, accounting, memory and idle-path distributions.

Post-audit polish is merged: deployed commit provenance, demo appliance CI, HTTPS HSTS,
a security policy, grouped dependency updates and MIT licensing. Dependabot runtime
ignore rules are on `chore/dependabot-rules` for review. This branch is not yet merged
or deployed.

## Targets (SLOs) we'll load-test against in step 12

- Gateway overhead (time added on top of the provider): under 10 ms at p99, excluding
  guardrails.
- Availability, excluding provider errors: 99.9%.

RPM uses GCRA with a bounded burst; TPM remains approximate. Exact overhead logs
and finer histogram buckets support the amended campaign.

The amended campaign evaluates total recorded overhead, including ordinary
guardrail scans. A separately guardrail-excluded timing distribution remains
unverified; completed benchmarking does not certify every target above.
