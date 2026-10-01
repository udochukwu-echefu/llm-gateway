# ADR 0028: Public exploration without public administrator credentials

- **Status:** Accepted
- **Date:** 2026-10-01

## Context

A portfolio visitor should explore the live console without receiving a credential that
can change shared data or spend money. Hiding buttons alone cannot protect an API.

## Decision

Add a `viewer` role whose nullable organization ID determines scope. Reject every unsafe
HTTP method centrally after authentication, before endpoint code, audit or idempotency.
Platform-wide viewers may read platform metadata; scoped viewers get the existing 404
isolation. Migration 0012 permits both scopes and refuses downgrade while any viewer row
exists, even revoked rows. CLI issuance uses the same hashed-secret storage as other roles.

The console's public demo sign-in selects a server-only key. Both Node entry points check
`/admin/v1/me` before loading Next or opening a listener. Only viewer roles with the expected
scope are accepted; the optional org key must name Northwind Health. Each sign-in rechecks
that condition. Browser responses include allowlisted identity, never the key. Demo
sessions expire absolutely after two hours and after thirty minutes idle. Key sign-in
is disabled by default in demo mode. The existing Origin, nonce CSP and socket-derived
throttle remain. Demo attempts, including successes, count toward the ten-per-minute
quota because visitors have no credential to guess. Browser mutation controls remain
visible but disabled; the BFF also refuses viewer writes before forwarding.

The owner superseded the VPS/Caddy design with a portable appliance on InstaCloud.
Every web service gets a public URL and there is no documented private network between
them ([deployment docs](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/deploy.md)).
One non-root container therefore holds console, gateway and fake provider. Only console
binds 0.0.0.0:3000 (matching injected PORT/EXPOSE); every other listener binds loopback.
The fake-provider allowlist is exactly `http://127.0.0.1:18000/v1`, rechecked after
secret-store resolution. Synthetic placeholders are not paid-provider credentials.

The stdlib supervisor validates config, waits at most 30 seconds for dependencies, runs
Alembic under an advisory lock, then appends only days after the latest synthetic day.
Seeder sign-in keys are skipped; managed remote DB seeding needs both explicit demo flags
and disabled sign-in-file output. Generic/local seeding still rejects remote databases.
Boot helpers discard stdout/stderr and send keys through a checked anonymous pipe.
Each boot creates platform/Northwind viewers and a Support tenant key with a boot-ID name;
plaintext lives only in memory and relevant child environments. Revoke only appliance keys
older than 24 hours, not fresh overlapping boot keys. Exactly one steady-state instance is
required. History, revoked key metadata and audit events grow; retention remains an operator task.

The console projects demo viewers to friendly visitor display names without changing
their key ID, role or organization scope. Internal boot-ID key names remain unchanged
for rotation and auditing; they are not the visitor's display name. All sidebar identity
names wrap within the sidebar, with their complete display value available via title.

Create compute with `--no-always-on`: it sleeps after five router-idle minutes and a request
cold-starts it in a few seconds ([operations docs](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/operate.md)).
No cron: top-up happens on wake. The traffic child sends three initial requests, then a
jittered 50–70-second interval internally; that traffic does not keep the router awake.
Any child exit fails the appliance. SIGTERM stops traffic/console, drains gateway usage,
then stops the fake provider within a shared bounded shutdown budget.

Managed Postgres is reachable on 5432 with credentials. Use a strong platform-generated
password and TLS where supplied, never real customer data. Synthetic data and hashed keys
make that exposure an accepted demo risk, not a production database recommendation.
Private Redis and server-only pepper/cache/session secrets are explicitly bound/configured.
The local test Compose profile publishes only loopback console port 3300; no Caddy remains.

This startup-migration choice deliberately differs from InstaCloud's generic advice to
migrate separately: the owner requires a self-bootstrapping appliance with bounded locking.
Updates must remain schema-compatible during overlap; failure never starts the console.

## Consequences

Public synthetic metadata can be scraped. Reads, exports and audit verification still
consume CPU/database capacity. Use platform firewall/DDoS controls for sustained abuse.
Per-process login throttling is not a distributed denial-of-service defence. Docker/root
administrators can inspect secrets; encrypted cookies are still replayable bearer tokens.
Changing the edge topology requires revisiting forwarded-IP trust, not merely adding a CDN.

## Alternatives considered

- Publish a platform key or rely on disabled buttons: gives strangers mutation authority.
- Use real providers: makes a portfolio visit a cost-abuse opportunity.
- Reset every day: unnecessary for viewers and would invalidate stable resource IDs.
- Extend local Compose directly: risks inheriting host port publication.
- Separate web services: exposes the console-to-admin link on this platform.
- Cron refresh: requires a public HTTPS hook and wakes an otherwise idle demo.
- Persistent plaintext boot-key files: unnecessary when children share one parent process.
