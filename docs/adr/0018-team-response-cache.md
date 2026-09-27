# ADR 0018: Exact-match responses isolated by team

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Re-embedding unchanged documents repeats paid work. Other applications may make the same
request but have no right to see the first application's answer.

## Decision

Cache complete embeddings by default and nonstreaming chat only with `x-lgw-cache: enabled`.
`x-lgw-cache: disabled` opts out of both. Never cache streams, `n > 1`, errors, oversized
responses, or a fallback result under the original model. A stream has already sent headers
and may fail after sending partial content; replay would need a recorded, validated complete
sequence with correct timing, usage and disconnect semantics. This is deferred.

Use exact canonical requests, the selected concrete model, the selected provider's options
and catalogue version in a SHA-256 fingerprint. Never store prompt text in the Redis key.
The prefix includes the verified team UUID: even two teams in one organization cannot share
entries. An HR team's answers are not the engineering team's business. Wider sharing is
deliberately not offered. A fallback answer belongs to a different model: storing it under
the original would silently serve that different model to the next caller.

Count RPM before cache lookup; hits skip budget, TPM, lease and provider, but generate a
zero-cost receipt with current-price estimated savings. TTL defaults to one hour (at most
seven days). Admin purge scans only resolved team UUIDs. Concurrent writes may repopulate
after a purge; stop writers first if strict invalidation is required.

## Consequences

Exact matching intentionally misses near-identical requests. Semantic caching is excluded:
a subtly different question can need a different answer, and similarity cannot guarantee
correctness or safe separation. Catalogue changes change the key; the TTL also bounds
staleness when a provider silently changes weights without a catalogue revision.

## Alternatives considered

- Organization-wide sharing: rejected; team boundaries are confidentiality boundaries.
- Cache every chat response: rejected; nondeterministic output must not freeze silently.
- Cache streamed output: deferred until validated replay semantics are designed.
