# Roadmap

Each step ends with tests, docs and a working gateway.

| # | Step | Status |
|---|---|---|
| 1 | Proxy to one provider with streaming, request IDs, structured logs, error mapping, CI | ✅ Done |
| 2 | Canonical OpenAI-compatible schema (chat, tools, structured output, embeddings), pass-through for provider-only fields | ✅ Done |
| 3 | Provider adapters: Groq, Gemini, DeepSeek, OpenAI | Next |
| 4 | Tenants and virtual API keys (inbound), secret store for provider keys (outbound) | |
| 5 | Model catalog with prices; token and cost tracking, written to Postgres off the request path | |
| 6 | Rate limits (requests and tokens per minute), concurrency limits, budgets, all in Redis | |
| 7 | Retries, circuit breakers, provider fallback | |
| 8 | Metrics (Prometheus), tracing (OpenTelemetry), audit log | |
| 9 | Model routing and per-team model access policies | |
| 10 | Caching, isolated per tenant | |
| 11 | Guardrails: PII redaction, content filtering, data residency | |
| 12 | Admin API, usage dashboard, load test report against our targets (SLOs) | |

## Targets (SLOs) we'll load-test against in step 12

- Gateway overhead (time added on top of the provider): under 10 ms at p99, excluding
  guardrails.
- Availability, excluding provider errors: 99.9%.
