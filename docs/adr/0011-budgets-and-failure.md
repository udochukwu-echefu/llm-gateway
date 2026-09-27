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

An existing Redis month key can survive a Redis outage while fail-open requests are
still written to Postgres. A lifespan-owned worker reconciles active teams in the
background every five minutes by default: `SUM(cost_usd)` for the UTC month plus the
local usage writer's not-yet-committed priced receipts. The writer's settlement lock
keeps a batch from moving from memory into Postgres between that SQL query and the
pending-receipt snapshot. Response finalization attempts the Redis increment **before**
enqueueing the receipt, so a pending receipt cannot be included by reconciliation and
then incremented for the first time afterward. One replica at a time holds the same
per-team rebuild lock (with an owner token); the Redis correction Lua script uses
exact integer-string comparison and only raises a counter, never lowers it. This
preserves spend recorded by another replica or in flight during the SQL snapshot.

| Key | Value | Expiry |
|---|---|---|
| `lgw:budget:<team UUID>:<YYYY-MM>` | pico-dollar integer | first day of next UTC month + 60 seconds |
| `lgw:budget:<team UUID>:<YYYY-MM>:alert` | one-time warning marker | first day of next UTC month + 60 seconds |
| `lgw:budget:<team UUID>:<YYYY-MM>:lock` | rebuild/reconciliation owner marker | 5 seconds |

At or over the budget admission blocks until next month. A missing or NULL cost cannot
be charged: `stream_incomplete` and `usage_missing` are not free, just unknown. In-flight
calls also are not included at admission, and the step 5 queue can still be waiting to
write to Postgres. Budget enforcement is a guard rail, **not** a transactionally exact
ceiling or an invoice ledger. A rebuild from Postgres after losing Redis can miss costs
still in that queue; reconcile invoices and monitor queue drops.
Budget drift caused by a Redis outage heals within a reconciliation interval once
the affected receipts are durable in Postgres (or still pending on the reconciling
replica). A first missing-key rebuild is capped at 200 ms, including its SQL query
and Redis lock wait; timeout applies the configured fail mode and logs a rate-limited
error. Reconciliation is off the request path.

The correction is deliberately conservative: it never reduces an existing Redis
counter. A receipt permanently lost by the best-effort writer can therefore leave a
budget **over**count until month-end. Another replica's queued receipt whose Redis
increment failed may be invisible to the current lock holder until it is flushed;
the next reconciliation after that flush includes it. Unknown-cost records remain
unknown, not zero-cost usage.

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
