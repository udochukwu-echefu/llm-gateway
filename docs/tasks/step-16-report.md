# Step 16 review report

Branch: `feat/step-16-public-demo-mode`. Portable-appliance amendment supersedes the
original VPS/Caddy sections. **Not deployed, pushed or merged. Awaiting owner review.**

## Built

- Nullable-scope `viewer` role, migration 0012/downgrade refusal, CLI issuance and central
  unsafe-method denial before endpoint handlers, audit or idempotency effects.
- Server-only Explore sign-ins; startup/per-login role and scope checks; Origin checks,
  successful-sign-in throttle, two-hour absolute/30-minute idle demo session; normal
  sign-in remains the default when demo mode is off. Viewer BFF mutation defense.
- Visible, disabled mutation controls with explanations. Reads, search, CSV, identity,
  role-appropriate settings and theme/preferences stay usable.
- Exact loopback fake-provider startup guard, also after secret-store resolution.
- Non-root digest-pinned multi-stage appliance; console standalone, Python venv and
  fake provider in one image. Only console is public on 3000; all other sockets loopback.
- Stdlib supervisor; dependency wait, locked migrations, lazy append-only synthetic-day
  top-up, per-boot memory-only keys, 24-hour appliance-only revocation, ordered bounded
  shutdown and whole-container failure when a child exits. No cron or Caddy.
- Local `demo-test` appliance/Postgres/Redis profile, browser tests/no-leak scan, break
  runner, local measurement script and four safe curated screenshots.
- Cited InstaCloud CLI/DNS/update/rollback/down runbook with a same-image Docker fallback;
  architecture, ADR 0028, threat model, README and roadmap updates.

## Gateway gates

Final command output (normal tests never call real providers):

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
436 files already formatted
uv run pyright
0 errors, 0 warnings, 0 informations
uv run pytest -q
1400 passed, 341 skipped, 40 deselected in 27.47s
```

Started only the existing local dependency services with
`docker compose up -d postgres redis` (both reported Running; none stopped). DB fixtures
create/drop their own `gateway_test_<uuid>` databases; the URL names the connection
database, **not a migration/seed target**. The owner's `gateway` DB was never seeded or
migrated. DB and Redis invocations ran sequentially before e2e:

```text
GATEWAY_TEST_DATABASE_URL=... uv run pytest -q -m db
275 passed, 11 skipped, 1487 deselected in 71.26s
GATEWAY_TEST_DATABASE_URL=... GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run pytest -q -m redis
66 passed, 1707 deselected in 52.96s
```

The 40 ordinary deselections are opt-in live tests; no live provider tests were run.
The appliance's demo-seeding tests use separate function-scoped disposable DBs so boot
keys/history cannot alter the older shared seeder tests.
The eight new remote-flag unit cases were added after the DB/Redis runs; they are not
DB/Redis-marked, so the selected DB/Redis test sets are unchanged.

## Console gates (Node 24.15.0)

```text
npm run format:check: All matched files use Prettier code style!
npm run lint: eslint . (exit 0)
npm run typecheck: tsc --noEmit (exit 0)
npm test: Test Files 23 passed (23); Tests 117 passed (117)
npm run build: Generating static pages using 11 workers (16/16); build exited 0
```

Build used synthetic placeholder session settings, ADMIN_API_URL loopback and console
origin on 3300. No dependency additions or lockfile changes; no host package/CLI/browser
installation. Docker build stages use the existing exact lockfiles.

### Every normal-console e2e test

`CONSOLE_TEST_PORT=3300 npm run test:e2e`: **28 passed (1.4m)**, final rerun passed.

1. requests-log filtering URL chips and complete attempt detail drawer
2. CSV export contents match the current request and audit filters with rounded machine-readable numbers
3. analytics date range group switches and unknown first-byte gaps
4. settings platform and org roles preferences persistence and forbidden API
5. keys search team status filters and last-used metadata
6. audit filters action actor target dates URL and safe event drawer
7. command palette page navigation and API-enforced organisation scoping
8. platform workflow
9. one-time key dialog
10. org-admin isolation and URL tampering
11. security headers and CSP
12. cookie flags and cross-origin POST
13. revocation logs out
14. login throttle and no shared-IP lockout
15. demo tour every screen and tab as platform admin
16. demo tour every screen and tab as org admin
17. empty workspace guides first team key request and unmatched audit filter
18. Overview landing numbers match the seeded org usage API and org scope
19. Overview platform landing includes all organisations and recent activity
20. org policy and team intersection enforced by public API
21. guardrail tightening and weaker choice has no effect
22. EU residency shrinks usable models using the API view
23. Singapore residency is offered from the authoritative catalog and can be saved
24. two browser contexts preserve the first policy and keep the conflicted draft
25. cache purge requires a typed name and reports its count
26. org admin cannot view or edit another org policies by URL tampering
27. every policy write and cache purge appears in the audit log
28. unsaved policy changes warn before tab page and browser Back navigation

### Every appliance public-demo e2e test

`CONSOLE_TEST_PORT=3300 CONSOLE_CURATED_SCREENSHOTS=1 npm run test:e2e:demo`:
**6 passed (33.6s)**, including waits for actual rendered data and nonempty mutation
controls before asserting their disabled state. Screenshots were reviewed, not loading
placeholders. Public `/admin/v1/me` redirects to console login HTML, not gateway admin JSON.
An initial assertion incorrectly expected 404 instead of this protected-console redirect;
the final test checks the redirect destination and HTML response and drains the body for
the shared scan. It does not relax a gateway exposure test.

1. Explore button signs in as platform viewer
2. public demo tour visits every screen as platform viewer
3. Explore button signs in as org viewer
4. public demo tour visits every screen as org viewer
5. public viewer direct BFF mutation attempts return 403
6. public demo hides paste-key form and disables key login route

No-leak totals (shared scanner, no bypass for the new specs): normal **2830 responses**,
exactly **1** permitted one-time key-creation response, **zero leaks**. Final demo
run: **679 responses**, **0** permitted responses, **zero leaks**. Combined final runs:
**3509 browser responses**, exactly **1** permitted creation response, **zero leaks**.
Boot keys are never extracted from the appliance or saved to host fixture state.

## Viewer matrix

OpenAPI inventory matches **33 method/route pairs**, each explicitly marked viewer read
or deny. **39 cases per viewer scope** include the six If-Match policy variants: 19 reads,
20 denials. Missing a route or a viewer policy fails completeness; a regression test
deliberately omits a policy and checks that assertion.

| Operation | Platform viewer | Northwind-scoped viewer |
|---|---|---|
| me, catalog, global search | 200; platform metadata | 200; search rows scoped before matching/limit |
| org/team/key lists, policies, limits, budgets, usage, requests/detail, analytics | 200 across orgs | 200 own; 404 other org/resource |
| org list / audit list | 200 global | 200 own rows; tested against matching org-admin scope |
| settings / providers / audit verification | 200 | 403 |
| Any registered POST/PUT/DELETE (including If-Match/idempotency headers) | 403 `read_only_admin` | 403 `read_only_admin` |
| Missing credentials | 401 | 401 |

Mutation matrix hashes all mutable organization/team/key/limit/audit/idempotency state
before/after: denied requests have no effects. The old platform/org-admin matrix still
passes. Scoped viewer key prefix/ID lookup and resource checks inherit existing 404 isolation.

## Break checks (sources restored)

`npm run test:break:demo` deliberately applies each change, requires a failed behavior
assertion (not syntax/import failure), and restores the original file in `finally`:

| Break | Catching test |
|---|---|
| (a) Remove central viewer unsafe-method guard | `tests/admin_api/test_authorization.py::test_viewer_authorization_matrix` (POST cases) |
| (b) Demo response includes selected key | `tests/lib/demo.test.ts`: demo sign-in uses a server-side key and returns only identity |
| (c) Startup accepts platform-admin key | startup refuses a platform-admin demo key and wrong viewer scope |
| (d) Route active while DEMO_MODE off | demo route is 404 when demo mode is off |
| (e) Appliance admin binds 0.0.0.0 | `tests/demo/test_appliance.py::test_appliance_internal_listeners_bind_only_loopback` |
| (f) Boot key printed to stdout | `test_boot_keys_use_only_private_pipe_never_stdout_or_disk` |
| (f) Boot key written to disk | same test, directory must stay empty |

```text
All seven demo mutations caught; every source restored.
```

The initial startup break test masked platform-key acceptance with a later org-key
failure; isolating that startup check made the mutation fail for the right reason.
The existing `npm run test:break:console` also passed all five completeness mutations
after its seeder/search targets were updated; every source restored.

## Compose, builds and appliance measurements

```text
docker compose -f deploy/demo/compose.yaml --profile demo-test config --quiet
(no output; exit 0)
```

Local profile publishes only 127.0.0.1:3300:3000. Its own Postgres/Redis publish no ports;
no owner services/ports are stopped or used. It removes only its disposable containers,
network and volumes. Supervisor tests cover dependency timeout/client closure, migration
lock and unlock-on-failure, child crash, credential environment isolation, output
discarding, loopback binds, signal order, console timeout and child signal-delivery races.
An eight-case callable-seeder test checks every combination of the three remote safety
flags; only the complete opt-in reaches an intercepted first I/O call (no network).

Native arm64 Docker build and dual-platform linux/amd64+linux/arm64 OCI export succeeded.
The OCI tar is outside the repo in the approved temporary directory; no registry push.
amd64 build was emulated, **not** a native amd64 runtime test.

Final measured arm64 appliance (`uv run python -m deploy.demo.measure`):

| Measurement | Result | Target |
|---|---|---|
| First provision to /login HTTP 200, dependencies warm but DB empty | 9.453 s | separate baseline |
| Cold container/process start, Postgres warm and history already seeded | 5.612 s | <=10 s: met |
| Whole-appliance Docker memory after 65 s awake | 236.2 MiB | <=1 GB: met |
| Local Docker image size (`Size`, uncompressed layers) | 624,223,325 bytes (~595 MiB) | report only |

Docker Desktop memory sample excludes managed Postgres/Redis and platform routing. No
Docker/network blocker was substituted with invented results; the initial uv-base pull
was slow (651 seconds) but completed. Download/build time is not cold-start time.

## Decisions the spec left open

- Viewer scope uses nullable organization ID, not the spelling of the role. Scoped
  viewers cannot see platform diagnostics; all unsafe methods receive the same code.
- Gateway uses OpenAI error envelope; BFF uses existing console error shape with 403/code.
- Shared existing throttle is ten sign-ins/minute/socket-derived client, successful
  Explore sign-ins count too. Trust forwarded IPs only after verifying platform topology;
  default zero may share a router-IP quota. No unverified platform WAF/body-limit claims.
- PORT=3000 is mandatory in the first image to match EXPOSE and deployment --port.
  Internal ports are 18000/18090/18091/19464, not the owner's reserved ports.
- Startup keys are fresh boot-ID names, issued after seeding establishes Northwind
  provenance; revoke only prefixed appliance keys older than 24 h. No boot-key files.
- Migrate under separate advisory lock 160028, seeder serialization lock 130025;
  dependency timeout 30 s, migration subprocess 45 s, boot helper 90 s. Child logs are
  intentionally discarded for secret safety; only safe supervisor messages remain.
- SIGTERM stops traffic first, then console/gateway/fake. Separate grace allocations
  prevent a hung console consuming the gateway's flush time, under a 20-second parent
  budget; host allowance 25 s. Core dumps disabled.
- Seeder remote opt-in requires demo deployment + remote flag + skipped sign-in files;
  local CLI remains local-only. Top-up retains existing policies/history and inserts
  only days after each org's latest synthetic day, through today. No pruning/cron.
- First seed budgets preserve existing illustrative stories; fake traffic uses Support,
  email redaction, rpm=5/tpm=10000/concurrency=1. Three initial requests then 50–70 s jitter.
- Digest-pinned multiarch base indexes; no runtime package manager/new dependencies.
- Managed bindings normalized to asyncpg URL (sslmode -> ssl); secrets generated locally
  and set through CLI stdin. Owner-approved setup remains separate from implementation.
- No extra viewer button/context state is hidden; theme/preferences and CSV stay active.
  Demo session flag, not role alone, determines actual shorter expiry display.

## Limits / unverified requirements

- No actual InstaCloud CLI install/login, service creation, secret setting, deploy,
  scaling, router sleep/wake, domain/DNS/certificate or rollback has been performed.
  The cited runbook explicitly labels all platform commands documentation-verified only.
- Single-instance status, credential-reachable managed Postgres/TLS and migration role/DDL
  permissions, private Redis,
  forwarded-header topology and platform abuse controls must be checked by the owner.
- Local target measurements are observations, not CI wall-clock assertions or cloud SLA.
- No live provider calls, k6 or py-spy measurement was needed/performed.
- History/audit/revoked keys grow without retention; old boot keys expire by later boot
  revocation, not a continuous timer. Process/root access can read memory/environments.
- Public URL remains a placeholder; all synthetic demo metadata is intentionally public.
- Rejected original VPS/Caddy/daily-refresh requirements are superseded by the amendment,
  not silently omitted. No known unsatisfied amended implementation requirement remains
  after final checks; cloud verification awaits separate owner authorization.

## Screenshots and commits

- [Explore login](../images/console-public-demo-login.png)
- [Platform viewer](../images/console-public-demo-platform.png)
- [Northwind viewer](../images/console-public-demo-org.png)
- [Locked mutation controls](../images/console-public-demo-read-only-controls.png)

The final response includes `git log --oneline main..HEAD`, including the report commit.
