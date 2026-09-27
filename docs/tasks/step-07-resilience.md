# Step 7: Retries, circuit breakers and provider fallback

- **Branch:** `feat/step-7-resilience` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis)

## Goal

Providers fail: they time out, return 503, rate-limit us, or go down for an hour. After
this step:

1. **Retries** recover from brief failures, but only where retrying is safe.
2. A **circuit breaker** per provider stops sending traffic to a provider that keeps
   failing, and probes carefully to see when it's back.
3. **Fallback** answers from an approved alternative model when the requested one is
   unavailable. It never happens silently, and never to a provider nobody approved.

## Decisions already made (binding; object in your report if you disagree)

### 1. What may be retried

An LLM call isn't free to repeat: if the provider processed it, we pay twice. So a
failure is retried only when we can be confident the provider did **not** do the work,
or told us to come back:

| Failure | Retry? | Why |
|---|---|---|
| Connect error, connect timeout, pool timeout | yes | the request never reached the provider |
| 429, 500, 502, 503, 504, 529 **before any response body** | yes | the provider refused or failed without serving |
| Read timeout (non-streaming) | **no** by default (setting `GATEWAY_RESILIENCE__RETRY_READ_TIMEOUTS=false`) | the provider may have finished and billed us |
| Any 4xx other than 429 | no | the request itself is wrong; repeating won't fix it |
| Anything after the first byte was sent to the client | **never** | the client already has part of an answer |

- Streaming: retries happen only inside `open_chat_stream`, before the client response
  starts (step 3's design already guarantees that point exists).
- Up to **2 retries** (configurable). Exponential backoff with **full jitter** (base
  0.25 s, cap 2 s). The architecture doc must explain the thundering herd problem jitter
  solves, in plain words.
- A provider `Retry-After` is honoured if it's within the cap. If it's longer, don't
  wait: treat it as an exhausted retry, so fallback can take over.
- **Retry budget (anti-storm):** per provider, retries may be at most 20% of first
  attempts over a rolling minute, in-process with an injectable clock. When the budget
  is spent, fail fast. Explain how unlimited retries turn a small outage into a big one.
- **One overall deadline per client request** (`GATEWAY_RESILIENCE__DEADLINE_S`,
  default 60). Each attempt gets only the time that's left. For streams, the deadline
  covers only the time until the first chunk.

### 2. Circuit breaker

- One breaker **per provider, per replica, in-process**. No Redis on this path: a breaker
  must keep working when shared infrastructure is failing. Document that replicas learn
  independently, and why that's acceptable.
- Counts as a failure: connect/timeout errors, 5xx, and 429. Doesn't count: other 4xx
  (client errors) and successful responses.
- States:
  - **Closed** → **open** when, over the last 30 s, there were at least 10 calls and
    ≥ 50% failed (all configurable).
  - **Open** for 30 s: calls fail immediately with **503** `provider_unavailable`
    (or fall back, see below), without touching the network.
  - Then **half-open**: exactly **one** probe request is allowed (concurrent requests
    must not all become probes). Success closes the breaker, failure reopens it.
- Log every state transition (`circuit_opened`, `circuit_half_open`, `circuit_closed`)
  with the provider and failure counts.

### 3. Fallback

- Fallback is **opt-in per model, in the reviewed catalogue**:
  `fallbacks = ["deepseek/deepseek-flash", "groq/openai/gpt-oss-120b"]` on a model entry.
  No fallbacks configured means no fallback.
- **Why opt-in:** fallback sends the user's prompt to a **different company**. That can
  break data-residency or contract rules (step 11 formalises this). Put this in the ADR
  and the threat model.
- Triggers: the requested model's breaker is open, or its retries ran out on a
  retryable failure. **Never** on a client error (4xx other than 429).
- Try targets in order. Skip a target when its provider isn't configured, its breaker is
  open, or it can't serve the request. Use the existing capability checks: e.g. a
  `json_schema` request can't fall back to DeepSeek. Each target gets its own retries,
  within the same overall deadline.
- The request is re-sent with the **target provider's** `provider_options` (ADR 0003
  was designed for this) and the target's model name.
- Clients can refuse fallback with the request header `x-lgw-fallback: disabled` (e.g.
  for evaluations that must hit one exact model).
- Transparency: the response `model` already names the model that actually served it.
  Also add `x-lgw-fallback-from: <requested model>` and `x-lgw-attempts: <n>` response
  headers whenever fallback happened or retries were used.
- Validation: every fallback target must be in the catalogue and of the same `kind`, a
  model can't list itself, and there must be no cycles. An invalid catalogue fails
  startup.

### 4. Accounting for multiple attempts

- **One usage record per provider attempt**, not per client request, because failed
  attempts can still be billed. Add `attempt` (1, 2, …) and `fallback_from` (nullable)
  columns with a migration. All attempts share the request ID.
- TPM and budget count each attempt's actual tokens and cost (step 6's `finish` must
  handle several records per request).
- The concurrency lease stays **one per client request**.

### 5. Layering

- Put the policy in its own package (e.g. `resilience/`: `retry.py`, `breaker.py`,
  `fallback.py`). Providers don't know about retries, and endpoints call one entry point
  (e.g. `execute_chat(...)`) rather than looping themselves.
- Injectable clock, sleep and random source everywhere, so tests are deterministic and
  fast.

## Tests required

1. Retry table: every row of decision 1 as its own parametrized case, asserting the
   number of provider calls.
2. No retry once a streamed byte has been sent, even if the stream then fails.
3. Backoff: the delays stay within the full-jitter bounds; `Retry-After` is honoured or
   triggers fallback when over the cap; the deadline cuts attempts short.
4. Retry budget: past 20%, retries stop; the budget recovers after the window.
5. Breaker: the full state machine with a fake clock; the minimum-calls rule; 4xx
   doesn't trip it; **exactly one probe** when 20 requests arrive while half-open.
6. Fallback: the order; skipping unconfigured, open-breaker and incapable targets; no
   fallback on 4xx; the opt-out header; target `provider_options` applied and others
   dropped; the response headers; the catalogue validation rules (self-reference,
   cycles, wrong kind, unknown target).
7. Accounting: a request with 2 failed attempts + 1 fallback success produces 3 usage
   records with the right attempt numbers, `fallback_from`, costs and statuses; budget
   and TPM include them all; exactly one lease is taken and released.
8. **Live:** with the Groq base URL overridden to a closed local port and Groq's model
   configured to fall back to DeepSeek, a real request succeeds through DeepSeek. Mark
   it `live`, and skip it when the DeepSeek key is missing.
9. Before reporting, temporarily break each of these and confirm a test fails: (a) retry
   a 400, (b) retry after the first streamed byte, (c) let every half-open request
   through as a probe, (d) fall back to a target that can't serve the request, (e) record
   only the final attempt.

## Docs required

- **ADR 0012:** the retry policy and why LLM calls aren't safely repeatable (the billing
  risk), plus jitter, the retry budget and deadlines.
- **ADR 0013:** the circuit breaker (per-replica, in-process) and fallback (opt-in,
  capability-aware, transparent).
- **`docs/architecture.md`:** a "Step 7" section in plain language. Use analogies: a
  fuse box for the breaker, a crowd rushing a door for the thundering herd, and a
  substitute teacher for fallback, including why the class should be told.
- **Threat model:** retry storms amplifying outages; fallback sending data to an
  unapproved provider; a client forcing fallback to a cheaper or weaker model (they
  can't: only the catalogue decides).
- **README:** configuring fallbacks, the opt-out header, the response headers, and the
  new error code. **Roadmap:** step 7 done, step 8 next.

## Out of scope

Hedged or parallel requests, cross-replica breaker state, cost-aware or latency-aware
routing (step 9), retrying mid-stream, alerting on breaker trips (step 8).

## Report back with

- Final output of the four gates, and the db, redis and live tests (using the exact
  AGENTS.md commands).
- The breaker and retry defaults as built.
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
