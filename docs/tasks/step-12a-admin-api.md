# Step 12a: Admin HTTP API and usage dashboard

- **Branch:** `feat/step-12a-admin-api` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis)

## Goal

Everything a platform team manages today goes through the `gateway-admin` CLI, run by
someone with database access. Companies need to manage the gateway from their own tools
(internal portals, scripts, CI). After this step:

1. An **admin HTTP API** exposes every CLI operation, with its own credentials and roles.
2. Org admins can manage **only their own organisation**.
3. A Grafana **usage dashboard** shows per-team spend, budgets, top models and cache
   savings, read from Postgres through a read-only database role.

## Decisions already made (binding; object in your report if you disagree)

### 1. One service layer, two front ends

- Move the logic the CLI performs into an admin service module (e.g.
  `src/llm_gateway/admin/service.py`, split by area if it grows past the size limits).
  **Both** the CLI and the HTTP API call it. No operation is implemented twice.
- The CLI keeps working exactly as before, and its existing tests must still pass
  unchanged, apart from import paths.
- Every mutation still writes its audit event **in the same transaction** (step 8).

### 2. A separate, private listener

- The admin API runs on its **own port** (`GATEWAY_ADMIN_API__PORT`, default 8081),
  bound to `127.0.0.1` by default (`GATEWAY_ADMIN_API__HOST`), in the same process,
  like the metrics listener. It's disabled when `GATEWAY_ADMIN_API__ENABLED=false`.
- It must **not** be reachable on the public API port. Test this.
- Path prefix `/admin/v1`. OpenAPI docs are served on the admin port only.

### 3. Admin credentials and roles

- Admin keys use the same scheme as tenant keys (HMAC with the pepper, key ID lookup,
  constant-time compare), but a **different prefix**: `lgwa_…`. They're stored in their
  own table (`admin_keys`: id, key_id, secret_hash, role, organization_id nullable,
  name, created_at, expires_at, revoked_at).
- Two roles:
  - `platform`: everything, all organisations.
  - `org`: only resources inside its own organisation. Any access to another org's
    resource returns **404** (not 403), so admins can't discover which org IDs exist.
    Explain this in the ADR.
- A tenant key (`lgw_…`) must never work on the admin API, and an admin key must never
  work on `/v1`. Test both directions.
- Bootstrap: `uv run gateway-admin create-admin-key --role platform|org [--org O] <name>`
  prints the key once. The first platform key can only be created via the CLI (with
  database access), never over HTTP.
- The **audit actor** for API calls is `admin:<key_id>` (replacing OS user for these),
  which is a real, verifiable identity. Update the threat model row about actor spoofing.
- Failed admin authentication uses the step 6 per-IP failure limiter (separate counter).

### 4. Endpoints (JSON, OpenAI-style error envelope)

Mirror the CLI:

```
POST   /admin/v1/orgs                         (platform)
GET    /admin/v1/orgs                         (platform: all; org: own)
POST   /admin/v1/orgs/{org}/teams
GET    /admin/v1/orgs/{org}/teams
POST   /admin/v1/orgs/{org}/teams/{team}/keys          -> returns the full key ONCE
GET    /admin/v1/orgs/{org}/keys?team=                 -> metadata only, never secrets
POST   /admin/v1/keys/{key_id}/revoke
PUT    /admin/v1/orgs/{org}/teams/{team}/limits        (and DELETE to clear)
PUT    /admin/v1/orgs/{org}/teams/{team}/budget
PUT    /admin/v1/orgs/{org}/model-policy     (?team=)   (and DELETE)
PUT    /admin/v1/orgs/{org}/guardrails       (?team=)   (and DELETE)
PUT    /admin/v1/orgs/{org}/residency        (?team=)   (and DELETE)
GET    /admin/v1/orgs/{org}/usage?since=&until=&group_by=
POST   /admin/v1/orgs/{org}/cache/purge      (?team=)
GET    /admin/v1/audit?since=&action=        (platform: all; org: own org's events)
GET    /admin/v1/audit/verify                (platform)
```

- List endpoints are **paginated** (cursor-based, default page size 50, max 500).
- Request bodies use strict Pydantic models. Money is a decimal string, never a float.
- Idempotency: `PUT` operations are naturally idempotent. `POST` creations accept an
  optional `Idempotency-Key` header, and repeating the same key within 24 hours returns
  the original result instead of creating a duplicate (store it in Postgres). Explain
  why in the ADR: network retries from admin tools must not create two keys.

### 5. Usage dashboard (Grafana on Postgres)

- Per-team data can't go in Prometheus (the cardinality rule from step 8), so this
  dashboard reads **Postgres**.
- Create a **read-only Postgres role** (`gateway_readonly`) through a migration, with
  `SELECT` only on the usage, team and organisation tables. **Not** on `api_keys`,
  `admin_keys` or anything holding secrets or hashes. Its password comes from the secret
  store / compose environment, not from the repo.
- Provision a Grafana Postgres data source using that role, plus a dashboard
  `observability/grafana/dashboards/usage.json` with: spend per team this month vs.
  budget, top models by cost, requests and tokens over time, cache hit ratio and savings,
  and unpriced usage (`usage_missing` / `stream_incomplete`) so it's never hidden. It
  has an org selector.

## Tests required

1. The CLI and API share the service: each operation tested once at the service level,
   plus thin API and CLI tests.
2. The admin API isn't reachable on the public port; `/v1` isn't served on the admin port.
3. Key separation: a tenant key is rejected on admin, and an admin key is rejected on `/v1`.
4. **Authorisation matrix:** for every endpoint, platform ✓, own-org ✓, other-org → 404,
   no key → 401. Build it as one parametrised table so a new endpoint without a row fails
   a completeness test (e.g. compare the table to the registered admin routes).
5. The key is shown once; list endpoints never return secrets or hashes.
6. Audit actor `admin:<key_id>` on API mutations; the same transaction as the change.
7. Pagination (cursor stability, max page size) and idempotency (same key → same result,
   different body with the same key → 409).
8. Read-only role (`db`): can `SELECT` usage; **cannot** read `api_keys` or `admin_keys`;
   cannot write anything.
9. Failed admin auth hits the per-IP limiter.
10. Before reporting, temporarily break each of these and confirm a test fails: (a) let an
    org admin read another org's teams, (b) accept a tenant key on the admin API, (c)
    return `secret_hash` in the key list, (d) grant the read-only role access to
    `api_keys`, (e) skip the audit event on an API mutation.

## Docs required

- **ADR 0022:** admin API (a separate listener, admin keys and roles, 404-for-other-org,
  a shared service layer, idempotency).
- **`docs/architecture.md`:** a "Step 12a" section in plain language: why admin traffic
  gets its own door, what an IDOR bug is (changing an ID in a URL to see someone else's
  data) and how the 404 rule and the auth matrix prevent it, and why the dashboard uses a
  read-only role.
- **Threat model:** admin key theft, IDOR, admin endpoint exposure, dashboard database
  credentials, and the updated actor-spoofing row.
- **README:** enabling the admin API, bootstrapping the first key, example curl calls,
  and opening the usage dashboard. **Roadmap:** 12a done.

## Out of scope

SSO/OAuth for admins, a web UI (beyond Grafana), admin key rotation automation,
multi-org admin keys.

## Report back with

- Final output of the four gates and the db, redis and live tests (exact AGENTS.md
  commands).
- The authorisation matrix (endpoint × role → expected status).
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
