# Step 10: Response caching, isolated per team

- **Branch:** `feat/step-10-caching` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis)

## Goal

Companies send the same requests over and over: re-embedding unchanged documents,
repeated classification prompts, retries from buggy clients. After this step the
gateway answers repeats from a cache: instantly, and at no provider cost. And a cached
answer can **never** reach another team.

## Decisions already made (binding; object in your report if you disagree)

### 1. What is cached

- **Exact-match only**: the same request, byte for byte after canonicalisation. Semantic
  ("similar question") caching is out of scope. Explain why in the ADR: it can return a
  wrong answer for a subtly different question.
- **Embeddings: cached by default.** They're deterministic, and re-embedding is the
  biggest real-world win (RAG pipelines re-processing unchanged documents).
- **Chat completions: cached only when the client opts in** with the request header
  `x-lgw-cache: enabled`. Model output varies on purpose, and silently freezing it
  would change application behaviour.
- **Never cached:** streaming requests (bypass them, and document the reason and a
  possible future replay design), `n > 1`, responses that aren't a complete success, and
  entries over a size limit (default 1 MiB).
- Clients can always refuse the cache with `x-lgw-cache: disabled`.

### 2. Isolation and the cache key

- The key is `lgw:cache:<team_id>:<sha256>`, where the hash covers the **canonical JSON**
  of: the endpoint, the **resolved concrete model** (after alias and weighted choice,
  never the alias name), every canonical request field **except** an explicit exclusion
  list (`stream_options`, `user`, `safety_identifier`), the serving provider's
  `provider_options`, and the catalogue version.
- **Team scope only.** Two teams in the same organisation never share entries. The ADR
  must explain why (an HR team's answers are not an engineering team's business), and
  that wider sharing is deliberately not offered.
- Canonical JSON: sorted keys, no insignificant whitespace, and a stable number format,
  so logically identical requests hash identically. Test key stability.
- The prompt must never appear in the key. It's hashed.

### 3. Encrypted at rest

- Cached values are customer data, and Redis snapshots land on disk. Encrypt every value
  with **AES-256-GCM** (`cryptography`), using a key from the **secret store**
  (`cache_encryption_key`, 32 bytes, base64). Store a key ID with each value so the key
  can be rotated: values encrypted with an unknown key ID count as misses.
- Bind the ciphertext to its Redis key via GCM associated data. A value copied to
  another team's key must fail to decrypt (count it as a miss and log a warning).
  Explain why in plain words.
- A missing or invalid encryption key fails startup when caching is enabled
  (`GATEWAY_CACHE__ENABLED`, default true). Caching can be switched off entirely.

### 4. Where the cache sits

```
authenticate → resolve alias → policy → RPM → cache lookup
   ├─ hit  → respond (no budget, no TPM, no lease, no provider)
   └─ miss → budget → TPM → lease → provider (retries, fallback) → store → respond
```

- A hit still counts toward **RPM** (it's a request), but **not** TPM, budget or
  concurrency, since it costs nothing.
- Store **after** a successful response, off the critical path where practical. A failed
  store must never fail the request.
- Only cache a response served by the **requested concrete model**. A fallback response
  must not be stored under the original model's key. Explain why (the next caller would
  silently get a different model's answer).
- **Single-flight (per replica):** identical requests arriving together while one is
  already in flight wait for that first result, instead of all calling the provider (the
  "thundering herd" again). Bound the wait by the request deadline, and if the leader
  fails, followers make their own call.
- Redis unavailable → **bypass the cache** (fail open, rate-limited log). The cache must
  never break or slow a request beyond the Redis timeout.

### 5. Accounting and visibility

- A cache hit writes a usage record with `outcome = "cache_hit"`, `cost_status =
  "cached"`, cost 0, the original token counts, and a new nullable `saved_usd` column
  (what the call would have cost at current prices). Migration required.
- The usage CLI shows cache hits and **total saved USD** per group.
- Response header `x-lgw-cache: hit | miss | bypass | disabled`.
- Metrics (bounded labels only): `lgw_cache_requests_total{endpoint, result}` and
  `lgw_cache_saved_usd_total{endpoint}`. Add a Grafana panel for the hit ratio and
  savings.
- Tracing: a `cache.lookup` span with a `result` attribute, and no key material or
  content.

### 6. TTL and purge

- A default TTL (`GATEWAY_CACHE__TTL_S`, default 3600), capped at 7 days.
- `gateway-admin cache purge <org> [--team T]` deletes that scope's entries (SCAN +
  UNLINK, never KEYS) and writes an audit event.

## Tests required

1. **Isolation:** team A's cached answer is never served to team B, even with an
   identical request, and the same for two teams in the same org. A value copied from A's
   key to B's key fails decryption and counts as a miss.
2. Key: stability (field order and whitespace don't matter), the exclusion list, alias →
   concrete model, `provider_options` included, and a catalogue version change →
   different key.
3. Rules: embeddings cached by default; chat only with the opt-in header; streaming, `n>1`,
   errors and oversize bypass; the `disabled` header is honoured.
4. **Encryption:** the raw Redis value contains no plaintext marker from the response, an
   unknown key ID is a miss, and a missing key fails startup.
5. Pipeline: a hit counts RPM but not TPM, budget or lease; a hit is served while the
   team is over budget (it's free); a fallback response isn't stored.
6. **Single-flight:** 10 concurrent identical requests → exactly 1 provider call; the
   leader fails → followers call the provider themselves.
7. Redis down → bypass with no error, and latency within the Redis timeout.
8. Accounting: a `cache_hit` record with `saved_usd`; the CLI shows the savings; metrics
   and the header.
9. Purge: deletes only the target scope, is audited, and uses SCAN (not KEYS).
10. Live: embed the same text twice through Gemini (or chat with opt-in) → the second call
    is a hit with no provider call (`live`).
11. Before reporting, temporarily break each of these and confirm a test fails: (a) drop the
    team ID from the key, (b) store plaintext, (c) charge budget on a hit, (d) cache a
    chat response without the opt-in header, (e) store a fallback response under the
    original key, (f) remove single-flight.

## Docs required

- **ADR 0018:** caching scope and rules (exact-match, team isolation, opt-in for chat,
  never streaming, no fallback storage).
- **ADR 0019:** cache encryption (AES-GCM, associated data binding, key rotation via key
  ID) and single-flight.
- **`docs/architecture.md`:** a "Step 10" section in plain language: what a cache is (a
  photocopy of an answer you already paid for), why team isolation matters, why the
  ciphertext is bound to its key (a sealed envelope addressed to one person), and how
  single-flight saves money.
- **Threat model:** cross-tenant cache leakage, cache poisoning, Redis snapshot exposure,
  stale answers after a model change, and the cache as a timing side-channel (a hit is
  faster, which is acceptable within a team; explain why).
- **README:** the headers, the purge command, and the settings. **Roadmap:** step 10
  done, step 11 next.

## Allowed new dependency

`cryptography`. Nothing else without justification.

## Out of scope

Semantic caching, caching streamed responses, cross-team or org-wide sharing, provider
prompt caching (a provider feature, already reported via `cached_tokens`), and cache
warming.

## Report back with

- Final output of the four gates and the db, redis and live tests (exact AGENTS.md
  commands).
- The canonical key field list as built.
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
