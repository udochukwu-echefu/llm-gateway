# ADR 0013: Local circuit breakers and explicitly approved fallback models

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Repeated calls to an unhealthy provider waste capacity. Switching providers can keep
requests working, but also sends customer content to a different company, potentially
violating residency or contractual restrictions.

## Decision

One in-process breaker per provider per replica observes network attempts, including
retries. Over a rolling 30 seconds, at least ten observations with at least 50% failures
open it for 30 seconds. Failures are connect errors, timeouts, upstream 429 and 5xx.
Other 4xx and successful responses are non-failures. A successful stream is observed
when it finishes; a streamed transport timeout counts as failure. Client cancellation
is not a provider failure. A cancelled half-open probe reopens the breaker, so its
reservation cannot become stuck. Invalid or truncated stream data alone is not one
of the binding table's counted failure categories.

After the open interval exactly one request acquires a half-open probe without an
await between checking and reserving. Success closes; failure reopens. Generation
numbers stop older in-flight completions from changing a newer circuit state.
Transitions log `circuit_opened`, `circuit_half_open`, and `circuit_closed`, with provider,
observation count and failures, without content or credentials. Rejected calls return
503 `provider_unavailable` without touching the network. Replica states intentionally
learn independently: recovery remains available during Redis outages and the cost of
several probes is bounded by the replica count.

Only the requested catalogue entry's ordered `fallbacks` list is considered. Defaults
are empty; no production fallback is enabled by this change. Do not recursively follow
a target's own alternatives: the original entry must approve every destination. All
targets must exist, share the source kind and form an acyclic graph without self-links.
Startup rejects invalid catalogues. Capability checks reuse the adapter's payload
validation, including provider options, before starting an attempt or recording usage.
Unconfigured, open-circuit, incapable and not-yet-priced alternatives are skipped.
An eligible alternative has its own retries but shares the original overall deadline.

Fallback triggers only on an open circuit or exhausted retryable failure; client
errors and unsafe-to-repeat failures stop execution. Clients may disable fallback with
`x-lgw-fallback: disabled`, but cannot select another destination using that header.
Options are rebuilt for the selected provider. The response model remains the actual
provider/model. Whenever retries or fallback were used, responses include both
`x-lgw-attempts` (network attempt count) and `x-lgw-fallback-from` (original model),
including terminal error responses. Retry-only responses also include the latter header
as required by the step 7 specification; it does not by itself prove a provider changed.

## Consequences

Opt-in catalogue review is a data-sharing approval, not just a reliability decision.
Approvers must check residency and provider contracts. The client is told about the
substitution and can refuse it. Full tenant-specific access policies are step 9 and
formal residency enforcement is step 11; neither is implied by this implementation.

A new process loses breaker history and retry credit. Breakers do not coordinate across
replicas or use Redis. A provider-wide breaker can also suppress a healthy model on a
provider whose other models fail, as required by this step's scope.

## Alternatives considered

- Redis-backed breakers: recovery would depend on another service during failures.
- Automatic or cheapest-provider substitution: sends data to unapproved companies and
  can silently alter output quality. Catalogue approval and response transparency win.
- Transitive or parallel fallback: expands approved destinations or bills duplicate work;
  ordered direct alternatives keep behavior reviewable and sequential.
