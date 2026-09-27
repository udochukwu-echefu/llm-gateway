# ADR 0012: Bounded retries for potentially billable model calls

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Repeating an LLM call may generate and bill a second answer. A timeout does not prove
that the provider stopped working. Recovery must limit both duplicate charges and the
extra traffic sent into an outage.

## Decision

Implement the step 7 binding table: connect errors, connect timeouts and pool timeouts
may retry, as may upstream 429, 500, 502, 503, 504 and 529 before serving a response.
Other 4xx never retry, including provider 401/403 mapped to gateway 502 and provider
408 mapped to gateway 504. Retain the original status and transport exception category
as internal error metadata; neither is inferred from the translated client status.
Read timeouts require explicit `GATEWAY_RESILIENCE__RETRY_READ_TIMEOUTS=true`.
Write timeouts and other transport failures do not retry.

Allow at most two retries per target by default. Full jitter selects a random delay
between zero and `min(2 seconds, 0.25 seconds × 2^retry_index)`. Injectable clocks,
sleep and randomness make policy tests repeatable. Retry-After accepts delay seconds
or an HTTP date; a delay within the cap is honored, and a larger delay exhausts that
target immediately. Invalid values use jitter. One 60-second deadline covers the
provider execution phase, including backoff and every fallback. Async cancellation
bounds in-flight operations by the remaining time, in addition to existing HTTP phase
timeouts. Deadline exhaustion returns `504 upstream_timeout` and never starts another
attempt. A delay that cannot fit exhausts the target, leaving remaining time for fallback.

A per-provider, per-process rolling 60-second retry budget admits no more than one
retry per five first attempts (20%). A fallback target's first network attempt is a
first attempt for its provider. Open circuits and capability skips earn no credit.
No initial retry credit is granted: a new replica needs five first attempts to allow
one retry. Reserving retry credit before sleep prevents concurrent requests from
overspending it; cancelled reservations are conservatively retained until expiry.
Unlimited retries can multiply traffic just as provider capacity falls, turning a
small outage into a larger one. Jitter prevents synchronized clients from retrying
at the same instant.

Streaming recovery ends when `open_chat_stream` returns. A wrapper enforces the same
deadline while waiting for the first canonical chunk, then removes the overall timer;
normal read-silence timeouts remain. Stream errors, including before that first chunk,
are terminal SSE errors after response headers start, never retries or fallback.

Every network attempt gets a separate receipt, sequential attempt number and the same
request ID. `fallback_from` is NULL for primary attempts and the original requested
model for alternative attempts. Status is the mapped client status for that attempt;
failed attempts keep their status even when a later attempt succeeds. Actual known
tokens and costs are added for every receipt, with one client concurrency lease.
Price periods are selected at the original request time. Migration 0004 gives existing
rows attempt 1 and NULL fallback origin. The usage CLI's existing `requests` aggregate
now counts provider attempts, not distinct client request IDs.

## Consequences

The binding retry status list is implemented, but a 5xx is **not proof** that no work
was performed or billed. Even these retries retain duplicate-billing risk. Existing
ADR 0009's `not_billed` classification for rejected statuses is a convention, not a
provider invoice guarantee; absent usage cannot establish the actual charge. Read
retries require the operator to accept an even clearer duplicate-charge risk.

Usage remains best effort and unknown usage remains unknown. Request validation and
authentication run before provider execution begins. For streams, response headers
may already be 200 when the first-chunk deadline produces an SSE timeout error.

## Alternatives considered

- Retry every error: amplifies load and can repeat paid work or invalid requests.
- Fixed exponential delays: align retry waves across clients and replicas.
- A Redis retry budget: introduces shared infrastructure on the provider recovery path;
  this step explicitly requires an in-process budget.
