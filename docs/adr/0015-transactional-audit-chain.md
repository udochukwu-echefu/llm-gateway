# ADR 0015: Transactional append-only administrative audit chain

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Creating keys or changing limits can spend money. A separate best-effort audit write could
leave a successful change with no history or a history entry for a change that rolled back.

## Decision

The repository appends exactly one audit event in each mutating admin transaction. Read-only
commands append none. Actions use CLI names: create-org, create-team, create-key, revoke-key,
set-limits, clear-limits and set-budget. Repeated successful revoke/clear commands are recorded
as operator actions even if state was already revoked/clear. Exceptions roll back both writes.

Migration 0005 creates `audit_events` and an UPDATE/DELETE rejection trigger. Appends acquire
Postgres transaction advisory lock `0x4C47574155444954` before reading the tail. The default
READ COMMITTED isolation sees the previous committed tail after waiting for the lock. Reserve
an identity sequence ID while holding it, then compute SHA-256 over previous hash's lowercase
hex text concatenated with canonical JSON UTF-8. Genesis is 64 zero characters. Canonical JSON
contains id, UTC microsecond timestamp, actor, action, target type/id and details, sorted keys,
compact separators and no NaN. Decimal amounts are strings. Sequence gaps are valid rollbacks.

Details are explicitly selected numeric changes; create/revoke events have empty details.
Public key IDs are targets, never key material or HMAC hashes. Names and arbitrary operator
strings are not copied into details, so credential URLs cannot enter through those fields.
Actor comes from validated `GATEWAY_ADMIN_ACTOR`, falling back to OS user plus hostname.
`gateway-admin audit list` filters by inclusive UTC date/action; `audit verify` reads one
consistent ordered snapshot and reports the first broken row with a nonzero CLI exit status.

## Consequences

The actor is a claim, not SSO-backed identity; operators can spoof it. The owner can disable
triggers, rewrite all hashes, truncate the table or delete a suffix undetectably without an
external trusted checkpoint. Restrict owner access and retain database backups/checkpoints.
The chain is tamper-evident against inconsistent edits, not a signature or immutable ledger.
One global pen serializes admin writes, which are infrequent; model requests do not take it.
No outcome migration is needed: usage outcome is already a VARCHAR, not a database enum.

## Alternatives considered

- Audit after commit: fails atomicity in either direction.
- Unlocked hash appends: concurrent transactions can fork the chain.
- Hashes without an append-only trigger: routine UPDATE/DELETE could silently destroy history.
- Signed external ledger/SSO: stronger provenance but outside this step.
