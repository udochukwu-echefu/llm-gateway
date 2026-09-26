# ADR 0006: Virtual keys with HMAC, a pepper and bounded positive caching

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

Clients need separate identities without giving them provider credentials. A stolen
database must not become a directory of usable client keys. Every check also has to be
affordable on the request path.

## Decision

Issue `lgw_<12 lowercase base32 chars>_<32 random bytes, base64url without padding>`.
The public ID indexes a Postgres row; the secret is returned once. Store only the binary
HMAC-SHA256 of the secret with a separate, 32+ byte server pepper. Verify hashes using
`hmac.compare_digest` and perform a dummy comparison for unknown IDs. The pepper never
goes into Postgres. Never log the secret or an unverified ID. Revoke without deleting.

Use a bounded per-process LRU cache only for successful verifications (default 10,000
entries, 30-second TTL). Store the hash and identity, but still compare the supplied
secret on every cache hit and recheck absolute expiry each time. Do not cache failures.

## Consequences

Password hashing (bcrypt/argon2) deliberately slows guesses of low-entropy human
passwords. Our machine-generated secret has 256 bits of entropy, so guessing is not
feasible; a fast hash avoids a slow operation on every request. The pepper means a
database leak alone cannot even check candidate secrets offline. A leaked database **and**
pepper together remove that additional barrier, but still do not disclose the random keys.
Keys cannot be decrypted or recovered: clients must save them at creation. Rotating the
pepper invalidates every existing key; plan coordinated re-issuance. Revoked keys can
continue working for up to the TTL **on each gateway replica**; expiry is checked even
for a cached key. Cached identity remains bound to the verified ID, never the bearer text.

## Alternatives considered

- Encrypt secrets for later retrieval: rejected; we never need to retrieve a client key.
- Cache negative lookups: rejected; unknown IDs could flood the cache.
- Check Postgres on every request: stronger immediate revocation but higher latency/load.
- bcrypt/argon2: suited to passwords, not unpredictable 256-bit tokens.
