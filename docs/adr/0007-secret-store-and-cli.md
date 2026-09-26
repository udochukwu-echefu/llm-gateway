# ADR 0007: Injectable secret store and offline tenant administration

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

Provider credentials, the database URL and the hashing pepper must be supplied by the
deployment, not embedded in application code. Administrators need a way to create and
revoke tenants and keys before an authenticated service can be used.

## Decision

Use the `SecretStore.get(name) -> SecretStr | None` protocol. Environment variables
preserve the existing provider configuration; the file implementation reads one mounted
file per secret, strips a single trailing newline and refuses group/other access to
both its directory and files. Both resolve the pepper, database URL and provider keys
at startup. Missing critical secrets fail startup. A cloud store needs only another
implementation of this protocol.

Use an `argparse`-based `gateway-admin` CLI for organizations, teams, key creation,
listing and revocation; it connects directly to Postgres. It prints the issued key on
one line once. There is no network-exposed admin HTTP endpoint until step 12.

## Consequences

Local `.env` remains convenient but must never be committed. File mounts fit Docker and
Kubernetes; restrictive permissions require setup by the operator. The CLI needs secure
host access and Postgres credentials, and administrative operations are not yet audited
(step 8). Operators must migrate the database before running the CLI or gateway.

## Alternatives considered

- One implementation tied to environment variables: prevents mounted-file deployments.
- HTTP admin API now: enlarges the network attack surface before admin authentication.
- AWS/Vault backends: deferred; the protocol leaves a clear extension point.
