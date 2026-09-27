# ADR 0019: Authenticated cache encryption and per-replica single-flight

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Redis can snapshot values to disk. Cached model output can contain confidential information;
and simultaneous identical misses can trigger many billable calls.

## Decision

Encrypt each value with AES-256-GCM using a base64-encoded 32-byte secret from the secret
store. Each envelope has a derived key ID and a fresh random nonce. Use the entire Redis
key as associated data: moving a sealed answer to a different team address makes its
authentication check fail, like a sealed envelope addressed to one person. Unknown key IDs
are misses after rotation, and invalid tags log metadata-only warnings and miss. Missing or
invalid secrets fail startup when caching is on. Redis failure bypasses the cache within
its timeout regardless of the limits fail policy.

One replica keeps a map from cache key to a pending leader result. Followers wait at most
the request deadline, then use the successful leader's answer; a failed leader lets them
make their own calls. The map is not cross-replica coordination: different replicas may
still issue concurrent calls. Values are stored synchronously with a short Redis timeout
before publishing the result to followers, so an immediate next request can see it.

## Consequences

Rotation invalidates old entries unless older encryption keys are retained by a future
key-ring implementation; no old key is needed to keep serving traffic. A stolen Redis
snapshot alone reveals ciphertext and metadata (team UUIDs and hashes), not responses.
Operators must protect the encryption secret and restrict Redis access. A timeout on the
cache cannot make the model request fail, but a bounded lookup and store add up to one
Redis timeout each on a miss. Single-flight is local and cannot prevent cross-replica
duplicates.

## Alternatives considered

- Plain Redis JSON: rejected because snapshots expose customer answers.
- A global Redis lock: rejected; failover and owner death complicate a best-effort cache.
