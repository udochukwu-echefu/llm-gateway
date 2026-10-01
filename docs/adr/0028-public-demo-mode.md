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

The demo uses a separate `deploy/demo/compose.yaml` rather than extending development's
published Postgres/Redis/API ports. Only Caddy publishes 80/443. All application services
use an internal network; Caddy has a separate edge network for certificate issuance.
Gateway demo configuration accepts only the exact fake-provider service URL, checked
again after secret-store resolution. No actual provider credential belongs on this VPS.
Synthetic provider placeholders are not paid credentials.

Daily 03:00 UTC refresh appends deterministic synthetic history instead of resetting
workspaces or rotating sign-in keys. Bootstrap and refresh set the seeder's sign-in-key
flag to zero. A tiny jittered traffic worker uses a private tenant-key file. Refresh does
not prune history, so disk use grows: monitor it and perform separately reviewed retention.

Bootstrap runs only on the server, keeps generated files root-owned with restrictive
permissions and captures CLI output. Persistent secret files let a rerun reuse keys;
explicit rotation is a separate operation. This is a single-VPS demo with backups, not
high availability or a real-provider production service.

## Consequences

Public synthetic metadata can be scraped. Reads, exports and audit verification still
consume CPU/database capacity. Caddy's standard build has no request-rate-limit directive;
use provider firewall/DDoS controls or an explicitly reviewed CDN setup for sustained abuse.
Per-process login throttling is not a distributed denial-of-service defence. Docker/root
administrators can inspect secrets; encrypted cookies are still replayable bearer tokens.
Changing the edge topology requires revisiting forwarded-IP trust, not merely adding a CDN.

## Alternatives considered

- Publish a platform key or rely on disabled buttons: gives strangers mutation authority.
- Use real providers: makes a portfolio visit a cost-abuse opportunity.
- Reset every day: unnecessary for viewers and would invalidate stable resource IDs.
- Extend local Compose directly: risks inheriting host port publication.
- Multi-server deployment: unnecessary complexity for this explicitly limited demo.
