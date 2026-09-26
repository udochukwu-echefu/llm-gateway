# Step 5: Model catalogue, token and cost tracking

- **Branch:** `feat/step-5-cost-tracking` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres)

## Goal

Turn the token counts we already log into money: **"Team X spent $4.20 today on
groq/openai/gpt-oss-20b"**. After this step:

1. The gateway has a **model catalogue** with per-token prices. Only catalogued models
   can be used, and `GET /v1/models` lists them.
2. Every request that reaches a provider produces **one usage record** in Postgres:
   who, which model, how many tokens, what it cost, and how it ended.
3. Usage records are written **off the request path**, so accounting never slows a
   request down or makes it fail.
4. Operators can see spend with `gateway-admin usage ...`.

## Decisions already made (binding; object in your report if you disagree)

### 1. The catalogue is a reviewed file in the repo

- `catalog/models.toml`, parsed with the standard library's `tomllib` and validated
  with strict Pydantic models at startup. An invalid catalogue fails startup.
- Each entry has: provider, provider model ID, kind (`chat` | `embedding`), price per
  **1M** input tokens, optional price per 1M **cached** input tokens, price per 1M
  output tokens (chat only), `source_url`, and `checked_on` (date).
  - Reject negative prices, duplicate `(provider, model)` pairs, unknown providers, and
    a cached-input price higher than the input price.
- The file has a top-level `version` (e.g. `"2026-09-26.1"`). Every usage record stores
  the version its cost was computed with.
- **Why a file and not a database table:** price changes go through code review and git
  history. That's the change-control trail finance will ask for. Put this in the ADR.
- **Prices must come from each provider's official pricing page**, with the URL and the
  date in the entry. If you can't find an official price, leave the model out and list
  it in your report. Never guess a price.
- Catalogue at least the models the live tests use (`tests/live/conftest.py`), plus
  whatever else you can verify.

### 2. Uncatalogued models are rejected

- A request for a model that isn't in the catalogue gets **404 `model_not_found`**, with
  a message saying it isn't in this gateway's catalogue. This check runs after routing
  resolves the provider and **before** any network call.
- Reasoning: the gateway can't account for what it can't price, and budgets (step 6)
  depend on it. It also gives companies an explicit allowlist of models.
- `GET /v1/models` (authenticated, OpenAI list format) returns catalogue models for
  **configured** providers only, with IDs in `<provider>/<model>` form.

### 3. Money is never a float

- Use `decimal.Decimal` everywhere for prices and costs, and `NUMERIC` in Postgres
  (enough precision for fractions of a micro-dollar, e.g. `NUMERIC(20, 12)`).
- Explain why in the architecture doc: binary floats can't represent most decimal
  fractions exactly (`0.1 + 0.2 != 0.3`), and those errors add up across millions of
  requests.
- The currency is USD. Store it on the catalogue so a second currency is a data change,
  not a code change.

### 4. How cost is computed

```
uncached_input = prompt_tokens - cached_tokens
cost = uncached_input × input_price
     + cached_tokens  × (cached_input_price, or input_price if none)
     + completion_tokens × output_price          # reasoning tokens are included here
all divided by 1,000,000
```

- **Normalise provider usage shapes in the adapters** before cost is computed. For
  example, DeepSeek reports cache hits as `prompt_cache_hit_tokens` rather than
  `prompt_tokens_details.cached_tokens`. Verify each provider's real usage shape from its
  docs **and** with the live tests (below). Don't assume they all match OpenAI.
- Keep the calculation a pure function with no I/O, fully tested with exact `Decimal`
  expectations.

### 5. One usage record per provider-bound request, including failures

A usage record is written for every request that was **sent to a provider**, whatever the
outcome. Requests rejected before any network call (auth, validation, uncatalogued
model) are not billing events. The audit log in step 8 covers those.

```
usage_records
  id (uuid pk), request_id, created_at (UTC),
  organization_id, team_id, key_id,
  provider, model, endpoint ('chat' | 'embeddings'), stream (bool),
  status_code, outcome, cost_status,
  prompt_tokens, completion_tokens, cached_tokens, reasoning_tokens (all nullable ints),
  cost_usd (NUMERIC, nullable), catalog_version,
  duration_ms, ttfb_ms
  indexes: (organization_id, created_at), (team_id, created_at)
```

- `outcome`: `success` | `upstream_error` | `client_disconnected` | `stream_error`.
- `cost_status`:
  - `priced`: usage was reported and the cost was computed.
  - `usage_missing`: the provider sent no usage (e.g. Gemini embeddings). Cost is NULL.
  - `stream_incomplete`: the client left before the usage chunk arrived. **We were
    probably still billed.** Cost is NULL, and the architecture doc must say plainly
    that this is a known accounting gap.
  - `not_billed`: the provider returned an error status. Cost is 0.
- **Never** store prompts, completions, or embedding vectors in usage records.
- Historical records keep the cost they were computed with. A later price change must
  not change past records (test this).

### 6. Writing off the request path

- An in-process **bounded** `asyncio.Queue` (default size 10,000) and a background
  writer task, started and stopped in the app lifespan. The writer inserts in
  **batches** (up to N rows, or every T seconds, whichever comes first; configurable,
  e.g. 500 rows / 1 s).
- Enqueue happens once the response has **fully finished**. For streams that's after the
  last byte, or when the client disconnects, so it covers every outcome above. Enqueuing
  must never block and never raise into the request.
- **Queue full:** drop the record, log an `error` event with the request ID, and count
  the drop. Never slow down or fail a user request because of accounting.
- **Database failure:** retry the batch with backoff (a few attempts), then log the
  failure with the number of lost records. Don't crash the writer.
- **Shutdown:** stop accepting records, then drain the queue with a timeout (e.g. 10 s)
  and log how many records were flushed and how many were lost.
- The ADR must be honest: an in-process queue **loses records if the process is killed**
  (SIGKILL, out-of-memory). Name the durable alternatives (a transactional outbox, Redis
  Streams, Kafka) and when a company would need them.

### 7. Reporting CLI

```bash
uv run gateway-admin usage <org> [--team T] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                 [--group-by team|key|model|day]
```

This prints request count, token totals and total cost per group, plus how many records
have a NULL cost (by `cost_status`), so the total never hides unpriced usage. The
aggregation runs in SQL (`GROUP BY`), not in Python.

## Verifying real usage shapes

You may run the live tests against real providers, which costs a few cents:
`uv run --env-file .env pytest -m live`. The owner's `.env` holds the keys.

- Extend the live tests to assert that each provider's streamed and non-streamed usage
  produces a `priced` record (or the documented status, like `usage_missing` for Gemini
  embeddings).
- Never print, log or copy key values. If a live test fails because a key is missing or
  invalid, report it rather than working around it.

## Tests required

1. **Catalogue validation:** every rejection rule in decision 1, the version is required,
   and the real `catalog/models.toml` passes validation.
2. **Cost function:** an exact `Decimal` table covering no cache, a partial cache, a
   cache without a cached price, reasoning tokens, embeddings (input only), and zero
   tokens.
3. **Usage normalisation per adapter** (DeepSeek cache fields, and anything else you
   find).
4. Uncatalogued model → 404 with no network call. `/v1/models` lists only configured
   providers' catalogue entries and requires authentication.
5. **Records per outcome:** success (non-stream and stream), upstream error
   (`not_billed`), client disconnect mid-stream (`stream_incomplete`), a stream error,
   and missing usage.
6. **Writer:** batching by size and by time, the queue-full drop (the request still
   succeeds and isn't slowed), retry then give up on DB errors, and drain on shutdown.
   Use an injectable clock/sink so these tests are fast and deterministic.
7. **`db` tests:** records are inserted with the correct types (NUMERIC round-trips
   exactly), the report aggregates are correct per `--group-by`, and a price change
   doesn't alter old records.
8. **Privacy:** a test proving that no prompt or completion text reaches a usage record.
9. **Migration:** it applies on top of step 4's schema. CI already runs `alembic
   upgrade head`.

## Docs required

- **ADR 0008:** the catalogue as a reviewed file, rejecting uncatalogued models, Decimal
  money, and the cost formula.
- **ADR 0009:** the async batched writer, its failure modes, and the durability
  trade-off.
- **`docs/architecture.md`:** a "Step 5" section in plain language. Explain why floats
  are wrong for money, what a background worker and a bounded queue are (use an
  analogy), what batching buys us, and the `stream_incomplete` accounting gap.
- **Threat model:** add rows for tampering with the catalogue (it goes through code
  review), queue flooding / losing usage records, and usage data as sensitive business
  data.
- **README:** catalogue editing, `/v1/models`, and the usage CLI. **Roadmap:** step 5
  done, step 6 next.

## Out of scope

Budgets and enforcement (step 6), rate limits, dashboards, invoices, multiple
currencies, estimating tokens when usage is missing, a durable queue.

## Report back with

- Final output of the four gates **and** the db tests **and** the live tests.
- Every catalogue entry with its source URL, plus the models you left out and why.
- Each provider's real usage shape as observed live, and how it's normalised.
- The design as built, every open decision you made, tests changed, and
  `git log --oneline main..HEAD`.
