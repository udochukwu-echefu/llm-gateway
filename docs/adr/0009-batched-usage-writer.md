# ADR 0009: Best-effort asynchronous usage writer

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

Waiting for a Postgres insert on every model response adds latency and makes a
database outage a customer outage. A streamed response may end normally, fail,
or be cancelled by the client; accounting must follow its actual ending.

## Decision

After the response finishes (or its stream disconnects), the ASGI middleware
enqueues one metadata-only record without waiting. A lifespan-owned writer flushes
up to a configured batch size or interval, whichever comes first. The queue has a
configured maximum; a full or stopped queue drops the record with a request-ID
error log and drop count. On database errors retry a batch three times with
exponential backoff, then count and log the loss. Shutdown stops admission and
drains for a configured deadline, logging flushed and lost totals.

## Consequences

Postgres failure and queue pressure cannot delay or fail a response. Accounting
is **best effort**: a SIGKILL or out-of-memory kill loses queued records; even
orderly shutdown may drop records at its deadline. A dropped batch is not silently
treated as zero spend. Alert on drops and reconcile provider bills; this is not an
invoice ledger. Teams requiring lossless records or hard budget enforcement need
a transactional outbox, Redis Streams, or Kafka, with idempotent consumers and
retention/recovery policies, before they rely on this data for billing.

## Alternatives considered

- Insert synchronously: rejected; Postgres becomes part of response latency.
- Unbounded queue: rejected; an outage could exhaust process memory.
- Durable broker now: deferred by the step's scope and deployment complexity.
