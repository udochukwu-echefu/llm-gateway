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
stuck if its owner crashed before DECR. Leases default to 15 minutes; deployments must
ensure the maximum possible stream duration is shorter than the lease TTL.

Every key begins `lgw:` and has a TTL:

| Key | Value | Expiry |
|---|---|---|
| `lgw:requests:<team UUID>:<UTC minute number>` | RPM bucket integer | 120 seconds |
| `lgw:tokens:<team UUID>:<UTC minute number>` | TPM bucket integer | 120 seconds |
| `lgw:auth-fail:<socket/proxy IP>:<UTC minute number>` | failed authentication bucket integer | 120 seconds |
| `lgw:leases:<team UUID>` | sorted set of lease IDs and expiry timestamps | lease TTL + 1 second, renewed on acquisition |

Keys are team-scoped, not key-scoped. A successful authentication does not erase failures.
Only the configured number of trusted proxy hops may contribute an X-Forwarded-For IP.

## Consequences

Atomic Lua prevents two replicas from both seeing nine requests and both incrementing
a limit of ten. Redis counters disappear after their TTL or Redis data loss. A response
lasting beyond its lease TTL could release capacity while still active; configure a
longer TTL for deployments with streams that can exceed 15 minutes.

## Alternatives considered

- A fixed window allows a burst at a minute boundary; a token bucket needs continuous
  refill accounting. The weighted sliding counter is small and predictable.
- Process-local counters cannot coordinate replicas. An INCR/DECR concurrency counter
  does not self-heal after a process crash.
