# ADR 0011: Budget guard rails and Redis failure behavior

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

The asynchronous usage writer reports costs but may be delayed or lose records. Redis
is fast enough for admission, but can be restarted or evicted.

## Decision

Store monthly spend as integer pico-dollars (10^12 per USD). Decimal prices convert
exactly to the NUMERIC(20,12) precision of Postgres; Redis INCRBY performs exact int64
addition. Avoid Lua floating-point arithmetic even for comparisons: decimal integer
strings are compared by length and then lexicographically. The signed int64 ceiling is
about $9.2 million per team-month. A missing month key is rebuilt using Postgres
`SUM(cost_usd)` under a Redis SET NX rebuild lock. The key is initialized with SET NX;
other replicas wait for the initialized value. Both budget check and spend increment
use an atomic Lua script. Alert marker SET NX emits one warning per team-month.

| Key | Value | Expiry |
|---|---|---|
| `lgw:budget:<team UUID>:<YYYY-MM>` | pico-dollar integer | first day of next UTC month + 60 seconds |
| `lgw:budget:<team UUID>:<YYYY-MM>:alert` | one-time warning marker | first day of next UTC month + 60 seconds |
| `lgw:budget:<team UUID>:<YYYY-MM>:lock` | rebuild owner marker | 5 seconds |

At or over the budget admission blocks until next month. A missing or NULL cost cannot
be charged: `stream_incomplete` and `usage_missing` are not free, just unknown. In-flight
calls also are not included at admission, and the step 5 queue can still be waiting to
write to Postgres. Budget enforcement is a guard rail, **not** a transactionally exact
ceiling or an invoice ledger. A rebuild from Postgres after losing Redis can miss costs
still in that queue; reconcile invoices and monitor queue drops.

The Redis failure policy defaults to fail open: prioritize availability, log errors at
most once per second, and let traffic pass. A bank concerned about cost exposure would
choose fail closed (`GATEWAY_LIMITS__FAIL_MODE=closed`), rejecting with 503; a startup
preferring continuity would commonly choose open. Redis outages do not make `/readyz`
unready in open mode; closed mode does.

## Consequences

Counters reset when Redis is lost until Postgres rebuilds budget spend. A process crash
may lose usage before the writer flushes; a hard financial cap needs a durable ledger
and reserved in-flight cost, outside this step.

## Alternatives considered

- Floating-point USD accumulates rounding errors and cannot represent pico-dollar
  thresholds above 2^53 exactly. Synchronous Postgres spend checks make every request
  wait for storage and still cannot know future output tokens.
