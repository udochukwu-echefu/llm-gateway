# ADR 0010: Redis counters and expiring concurrency leases

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Several gateway replicas must make the same admission decision, including when they
receive requests at the same instant. Postgres is too slow for per-request counters.

## Decision

Use Redis 7 and one Lua script per check-and-update operation. Scripts are loaded once
per process, called with EVALSHA, and reloaded on NOSCRIPT. A sliding-window counter
weights the previous 60-second bucket by the fraction still inside the last minute.
RPM increments at admission. TPM reads already recorded tokens at admission and
increments actual prompt plus completion tokens after the response finishes; concurrent
requests can overshoot TPM, bounded by how many leases are admitted. All scripts accept
the same injected clock from Python for deterministic edge tests.

Concurrency uses a sorted set of unique lease IDs scored by expiry, not a counter.
Acquire removes expired members, counts the rest and inserts a lease atomically. The
response middleware releases it only when the body ends, errors or disconnects.
Expiring leases recover from a crashed gateway: a plain INCR/DECR counter would remain
stuck if its owner crashed before DECR. Leases default to 15 minutes. An active request
renews its lease periodically, even while it waits for streamed chunks; a crashed
process stops renewing and its leases expire. Keep the TTL comfortably longer than
the maximum period a renewal task could be suspended by the deployment.

Every key begins `lgw:` and has a TTL:

| Key | Value | Expiry |
|---|---|---|
| `lgw:requests:<team UUID>:<UTC minute number>` | RPM bucket integer | 120 seconds |
| `lgw:tokens:<team UUID>:<UTC minute number>` | TPM bucket integer | 120 seconds |
| `lgw:auth-fail:<socket/proxy IP>:<UTC minute number>` | failed authentication bucket integer | 120 seconds |
| `lgw:leases:<team UUID>` | sorted set of lease IDs and expiry timestamps | lease TTL + 1 second, refreshed on acquisition and renewal |

Keys are team-scoped, not key-scoped. A successful authentication does not erase failures.
Only the configured number of trusted proxy hops may contribute an X-Forwarded-For IP.

## Consequences

Atomic Lua prevents two replicas from both seeing nine requests and both incrementing
a limit of ten. Redis counters disappear after their TTL or Redis data loss. A response
whose renewal task cannot run for longer than its TTL may release capacity while still
active; configure a TTL longer than the worst anticipated provider/client stall.

## Alternatives considered

- A fixed window allows a burst at a minute boundary; a token bucket needs continuous
  refill accounting. The weighted sliding counter is small and predictable.
- Process-local counters cannot coordinate replicas. An INCR/DECR concurrency counter
  does not self-heal after a process crash.

## Amendment: exact RPM admission (2026-09-30)

RPM now uses the Generic Cell Rate Algorithm (GCRA) in one atomic Lua script.
Each request books the next free time slot, spaced T = 60 / RPM seconds apart.
A request is admitted only if its slot is no more than (B - 1) slots ahead.
Redis TIME supplies the clock, so replica clock skew cannot change the decision.
For any interval W the bound is W / T + B; a rolling minute admits at most RPM + B.
This guarantee assumes Redis retains state and is available; fail-open outages
and state loss still permit uncounted traffic.

GATEWAY_LIMITS__RPM_BURST is a positive integer override; unset means
max(1, ceil(RPM * 0.05)). It controls the immediate burst, not a full minute's
initial allowance. Remaining requests means slots available now, and reset and
Retry-After mean seconds until the next conforming request, rounded upward.
The new key lgw:requests:<team UUID>:tat holds the theoretical arrival time and
expires when the booked slots drain. Older minute keys expire naturally.

TPM and failed authentication still use approximate weighted sliding counters.
TPM also records tokens after responses, allowing concurrent-call overshoot.
The first campaign's RPM counter reached 968 rolling-minute admissions at RPM
600 (61.3% overshoot) in one repetition: evidence that this counter algorithm
cannot promise exact rolling bounds. TPM itself was not load-tested; do not
misrepresent that RPM observation as a measured TPM overshoot.
Production Lua uses Redis TIME; tests replace its clock expression and hold expiry long enough to
prevent real-time scheduling pauses from clearing simulated-clock state, exercising the actual script against seeded random and saturated arrivals.

The bound covers admissions made under GCRA with retained Redis state. Old
weighted counters and new slot keys do not coordinate during a mixed-version
rollout. Drain old replicas and let their admissions age out for a full minute
before claiming the bound across the whole rolling window. The benchmark uses
fresh teams and only upgraded replicas.
