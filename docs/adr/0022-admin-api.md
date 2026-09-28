# ADR 0022: Private admin API with scoped keys and retry-safe creation

- **Status:** Accepted
- **Date:** 2026-09-28

## Context

The offline CLI requires database access. Internal portals and CI need an HTTP way to
manage the same resources, but tenant keys must never grant administrator privileges.
Network retries can repeat a create request after its response is lost.

## Decision

Run a second FastAPI application on a separate, loopback listener (port 8081 by
default). The public router has no admin paths, and the admin router has no `/v1`
model paths. Admin OpenAPI is available only on the private listener. The listener
is opt-in with `GATEWAY_ADMIN_API__ENABLED=true`; deployments must put their own TLS
and network access controls in front of it.

Admin keys use the tenant HMAC/pepper, public key ID, 256-bit random secret and
constant-time comparison scheme, with the distinct `lgwa_` prefix and `admin_keys`
table. The first platform key is issued by the database-connected CLI. There is no
HTTP admin-key creation route. A platform key can work across organizations; an org
key is permanently tied to one organization UUID. An org key probing another
organization's URL gets 404, even if that organization exists. This keeps names and
IDs from becoming an existence oracle. The audit actor for HTTP is the verified
`admin:<key_id>`, while the CLI retains its operator label. Failed admin guesses
use a separate Redis IP counter.

One admin service backs the CLI and HTTP routes; repositories still write each
mutation and its audit event in one Postgres transaction. Creation requests may
carry `Idempotency-Key`. A transaction-scoped advisory lock serializes retries of
the same actor, path and header. The request digest must match; a mismatch returns
409. The created row, audit event and replay record commit together. The record
expires after 24 hours, and a later keyed creation deletes expired records. A replay
record holds only resource IDs and non-secret metadata. For client-key creation, the
first response contains the full key; a replay returns the same `key_id` without the
secret and sets `secret_already_returned: true`. An admin tool that loses the first
response must revoke that key and create a new one. This avoids duplicate keys while
preserving ADR 0006's rule that the database never stores a usable key, even if both
the database and pepper leak. Other POST actions, such as revocation and purge, retain
their existing audited action semantics.

The Grafana usage dashboard reads Postgres via `gateway_readonly`, a role granted
SELECT only on organizations, teams, usage records and a budget-only view. The view
exposes the budget column without granting direct access to `team_limits`. The role
cannot read either key table or write data. Its password is supplied at migration and Grafana
startup through the deployment environment, never checked into the repository.

## Consequences

The private port and key prefix reduce accidental exposure; operators must still
restrict the listener, protect admin keys, and configure TLS at the edge. Org-scoped
404s prevent a direct IDOR probe, but timing and traffic patterns are not a formal
side-channel guarantee. The global audit chain remains serialized, and database
owners can still tamper with it as described in ADR 0015. Idempotency metadata is
replayable only to the same admin actor and header for 24 hours. Losing the first
key-creation response requires key revocation and replacement.
The reporting role has no login until a password is provided during migration.

## Alternatives considered

- Put admin routes on the public port: rejected because routing mistakes could expose
  administration to the customer-facing network.
- Reuse tenant keys: rejected because client applications must not administer tenants.
- Return 403 for another organization: rejected because it confirms that the ID exists.
- Keep CLI and HTTP mutation logic separate: rejected because audit and validation
  could drift.
- Store encrypted key responses for replay: rejected because a leak of Postgres and
  the pepper would reveal usable client credentials from idempotency rows.
