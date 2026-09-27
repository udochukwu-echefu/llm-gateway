# Step 6: Rate limits, concurrency limits and budgets

- **Branch:** `feat/step-6-limits-and-budgets` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres **and** Redis)

## Goal

Step 5 *reports* spend. Step 6 *protects* it. After this step:

1. Each team has **requests-per-minute (RPM)** and **tokens-per-minute (TPM)** limits,
   and a **maximum number of requests in flight** (concurrency).
2. Each team can have a **monthly USD budget**: a warning at a threshold (default 80%)
   and a hard block at 100%.
3. **Failed authentication is rate-limited per client IP**, which closes the brute-force
   gap in the threat model.
4. All counters live in **Redis**, so the limits hold across every gateway replica.

## Decisions already made (binding; object in your report if you disagree)

### 1. Redis and atomicity

- Add Redis (pin a 7.x or 8.x image, with a healthcheck) to `compose.yaml`, and use
  `redis` (redis-py, asyncio). Settings: `GATEWAY_REDIS_URL`, resolved through the
  **secret store**, since it may contain a password.
- **Every check-and-update is one atomic Lua script** (loaded once, called with
  EVALSHA, reloaded on NOSCRIPT). The classic bug is: two replicas both read "9 of 10
  used", both allow, and 11 requests go through. Explain this race in plain language in
  the architecture doc, and prove it can't happen (see Tests).
- Redis calls get a short timeout (default 50 ms), so a slow Redis can't add real
  latency.
- Key layout, all prefixed `lgw:`, with a TTL on every key so nothing grows forever.
  Document every key in the ADR.

### 2. Rate limits: sliding-window counter

- Use the **sliding-window counter** algorithm (current plus weighted previous fixed
  window). Explain it with a small worked example in the architecture doc, and compare
  it in one line with fixed windows and token buckets.
- **RPM** counts requests at admission.
- **TPM** can't be known before the call, since output length is unknown. So:
  - At admission, a request is allowed while the tokens *already recorded* in the window
    are below the limit.
  - After the response, the **actual** tokens (prompt + completion, from step 5's usage)
    are added to the window.
  - Document the consequence: TPM can overshoot by the tokens of requests already in
    flight, and that overshoot is **bounded by the concurrency limit**.
- Rejections return **429**, type `rate_limit_error`, code `rate_limit_exceeded`, with a
  `Retry-After` header (seconds, rounded up).
- On every authenticated `/v1` response, add OpenAI-style headers:
  `x-ratelimit-limit-requests`, `x-ratelimit-remaining-requests`,
  `x-ratelimit-reset-requests`, and the same three for `-tokens`.

### 3. Concurrency: self-healing leases

- In-flight requests are tracked as **leases** in a Redis sorted set (member = unique
  lease ID, score = expiry time), not a plain counter. Acquire = remove expired leases,
  count, add if under the limit, all in one Lua script.
- A lease is released when the response **fully finishes**, including streams, client
  disconnects and errors. It must never be released early at "headers sent".
- If a gateway process crashes, its leases expire on their own (default lease TTL
  15 minutes, configurable, and longer than the longest allowed stream). This is why a
  plain `INCR`/`DECR` counter is wrong: a crash leaves it stuck forever. Explain that in
  the ADR.
- Rejection: **429**, code `concurrency_limit_exceeded`, `Retry-After: 1`.

### 4. Budgets

- Monthly (calendar month, UTC) USD budget per team, with an alert threshold (default
  0.8).
- **Spend counter in Redis**, per team per month, incremented with each priced usage
  record's cost. Redis has no exact decimal type, so store an **integer number of
  pico-dollars** (1 USD = 10^12) and explain why: an integer is exact, and int64 still
  allows about $9.2M per team per month.
- **Postgres stays the source of truth.** If a team's month key is missing in Redis
  (after a restart, eviction or first use), rebuild it from `SUM(cost_usd)` for that
  month before checking. Use a lock or `SET NX` so only one replica rebuilds.
- Admission: allow while spent < budget. At or over budget → **429**, type
  `insufficient_quota`, code `budget_exceeded`, with a message naming the team's month
  and a `Retry-After` until the next month starts.
- Crossing the alert threshold logs **one** `budget_alert` warning event per team per
  month (dedupe it with Redis). Real alert delivery is step 8.
- Document honestly what budgets **can't** see: in-flight requests, `stream_incomplete`
  and `usage_missing` costs (NULL). A budget is a guard rail, not an exact ceiling.

### 5. Where limits are configured

- A new Postgres table `team_limits` (team_id pk/fk, rpm, tpm, max_concurrency,
  monthly_budget_usd NUMERIC, alert_threshold). A NULL column falls back to a global
  default from settings (`GATEWAY_LIMITS__DEFAULT_RPM`, etc.). A default of `0` or unset
  means unlimited. Make that explicit and tested.
- Load a team's limits **with the key lookup** and cache them in the verified-key cache,
  so there's no extra database query per request. Changes take effect within the cache
  TTL. Say so in the CLI output.
- CLI:

  ```bash
  uv run gateway-admin set-limits <org> <team> [--rpm N] [--tpm N] [--max-concurrency N]
  uv run gateway-admin set-budget <org> <team> <usd> [--alert-at 0.8]
  uv run gateway-admin show-limits <org> <team>     # config + live usage from Redis
  ```

### 6. Brute-force protection on authentication

- Count **failed** authentications per client IP (sliding window, default 20 per minute).
  Over the limit → 429 `rate_limit_exceeded` **before** any key lookup, so an attacker
  can't even make us query the database.
- Client IP: the socket address by default. Trust `X-Forwarded-For` only when
  `GATEWAY_TRUSTED_PROXY_HOPS=N` is set, taking the Nth address from the right. Explain
  why trusting it blindly lets attackers pick any IP.
- A successful authentication doesn't reset the counter (otherwise an attacker holding
  one valid key could keep resetting it).

### 7. Order of checks

```
IP failure limit → authenticate → budget → RPM → TPM → concurrency lease → provider
   → (response finishes) → release lease, record tokens (TPM) and cost (budget)
```

Cheapest and most protective checks come first. Requests rejected here are not
provider-bound, so they don't create usage records. Recording tokens and cost happens
after the response has finished and must never raise into the request.

### 8. When Redis is down

- `GATEWAY_LIMITS__FAIL_MODE=open|closed`, default `open`: if Redis errors or times out,
  the request is **allowed**, and an error is logged with a rate-limited log line, like
  step 5's queue drops. `closed` rejects with 503 `limits_unavailable`.
- Explain the trade-off in the ADR (availability vs cost control), and say which one a
  bank vs a startup would pick.
- `/readyz` reports Redis health, but a Redis outage does **not** make the gateway
  unready in `open` mode.

## Tests required

1. **The race, with real Redis:** team RPM = 10, fire 50 concurrent requests from
   **two separate app instances** sharing one Redis (to simulate two replicas). Exactly
   10 are admitted. The same for concurrency (limit 3, slow fake provider) and for the
   budget boundary.
2. Sliding window: exact expectations with an injectable clock at window edges.
3. TPM: admission uses recorded tokens, actual tokens are added after the response, and
   overshoot is bounded as documented.
4. Leases: released after a normal response, a finished stream, a client disconnect
   mid-stream, and an upstream error. A lease whose holder "crashed" (never released)
   expires after the TTL.
5. Budgets: pico-dollar arithmetic is exact; the rebuild from Postgres when the key is
   missing (a `db`+`redis` test); only one replica rebuilds; the alert is logged once;
   the block at 100% sets `Retry-After` to the month boundary; unknown-cost records
   don't count and that's documented.
6. Auth brute force: the 21st failure from an IP gets 429 without a key lookup (assert
   the repository wasn't called); `X-Forwarded-For` is ignored unless hops are
   configured, and handled correctly when they are.
7. Fail open and fail closed, with Redis unavailable.
8. Rate-limit headers present and correct on success, and `Retry-After` on each 429
   kind.
9. CLI set, show and clear, plus defaults and NULL fallback.
10. Markers: `redis` tests read `GATEWAY_TEST_REDIS_URL`, and skip locally or **fail in
    CI** exactly like `db` tests. CI gets a Redis service container.

## Docs required

- **ADR 0010:** the limiting algorithms, atomic Lua scripts, lease-based concurrency,
  and the Redis key layout.
- **ADR 0011:** budgets (pico-dollars, Postgres as source of truth, blind spots) and
  fail-open vs fail-closed.
- **`docs/architecture.md`:** a "Step 6" section in plain language, with analogies for:
  the race condition, sliding windows, leases (a library book with a due date), why
  budgets are guard rails, and fail open vs closed.
- **Threat model:** update brute force (now mitigated), and add rows for spoofing the
  client IP via headers, Redis outage, and a noisy team starving others (concurrency
  limits help).
- **README:** the Redis setup, the CLI commands, the headers, and the error codes.
  **Roadmap:** step 6 done, step 7 next. Update `AGENTS.md` commands with Redis.

## Allowed new dependency

`redis`. Nothing else without justification.

## Out of scope

Per-key limits (team-level only for now), per-model limits, alert delivery (email,
Slack), retries and fallback (step 7), a limits dashboard.

## Report back with

- Final output of the four gates, the `db` tests, the `redis` tests, and the live tests.
- The race-test numbers (admitted / rejected per scenario).
- The Redis key layout.
- Design as built, open decisions made, tests changed, and `git log --oneline main..HEAD`.
