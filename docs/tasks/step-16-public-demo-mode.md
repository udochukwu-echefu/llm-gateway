# Step 16: Public demo mode and deployment kit

- **Branch:** `feat/step-16-public-demo-mode` (from `main` at 79ebd95)
- **Read first:** `AGENTS.md`, `docs/architecture.md` (Steps 4, 12a, 12b, 13a-15),
  ADRs 0022-0027, `docs/security/threat-model.md`, `docs/deployment.md`,
  `loadtest/README.md` (the fake provider), `compose.yaml`, this spec
- **Needs:** Docker (Postgres, Redis), Node 24.15.0. No new npm or Python dependencies are
  expected; Docker images (Caddy) must be pinned. If something new is truly needed, stop and
  report.

## Goal

The owner wants a **public live demo** of the console at a URL like
`https://demo.udochukwu.cv`, linked from their portfolio. Anyone on the internet will visit
it. Today that is unsafe:

- a demo admin key can create orgs, revoke keys, change policies and purge caches, so one
  visitor could vandalise the demo for everyone;
- the only way in is pasting an admin key, and publishing a key is publishing a credential;
- a public server with real provider keys would let strangers spend the owner's money.

This step adds a **read-only demo mode** and a **deployment kit** so the demo can run on one
small VPS with Docker Compose and automatic HTTPS. The design iterations that follow will
then be the last thing before launch.

## Decisions already made (binding; object in your report if you disagree)

### 1. A read-only `viewer` admin role, enforced by the API

- New admin role **`viewer`**, platform-wide (`organization_id` NULL) or scoped to one
  organisation (`organization_id` set), mirroring `platform` and `org`.
- A viewer may call **every read** its scope allows: the same GETs as a platform admin
  (platform-wide viewer) or an org admin (org-scoped viewer), including `/settings`,
  `/providers` and `/audit/verify` for the platform-wide viewer.
- A viewer may **never mutate**: every POST/PUT/DELETE returns 403 with a stable code (e.g.
  `read_only_admin`), before any side effect, idempotency record or audit event.
- Enforce it **centrally in the admin API's authorisation layer**, not per route, so a
  future endpoint is read-only for viewers by default. Extend the authorisation matrix and
  its completeness test with a viewer column covering every route.
- **Migration:** 0009's check constraint only allows `platform` (no org) and `org` (with
  org). Add a migration (next number after the current head; check `alembic heads`) that
  also allows `viewer` with or without an organisation. Include a downgrade that refuses
  while viewer keys exist (say so clearly) rather than silently deleting them.
- CLI: `gateway-admin create-admin-key --role viewer [--org ORG] NAME`.

### 2. "Explore the demo" sign-in, without ever exposing a key

- New console settings, validated at startup like the others:
  - `DEMO_MODE` (default off);
  - `DEMO_VIEWER_KEY` (platform-wide viewer);
  - optional `DEMO_ORG_VIEWER_KEY` (an org-scoped viewer for Northwind Health, to show
    isolation);
  - `DEMO_ALLOW_KEY_SIGN_IN` (default **false** in demo mode).
- When `DEMO_MODE` is on, the login page shows clear buttons:
  - "Explore as platform operator (read-only)";
  - "Explore as Northwind Health org admin (read-only)", if configured.
  Each POSTs to `/api/auth/demo` with `{ "as": "platform" | "org" }`. The BFF signs the visitor
  in with the configured key **server-side**. The key never appears in HTML, JS, props or any
  response, exactly like 13a.
- **Fail fast:** at startup in demo mode, call `/admin/v1/me` with each configured demo key
  and **refuse to start unless its role is `viewer`** (and, for the org key, scoped to one
  org). A real admin key must never accidentally become the public demo login.
- Demo sessions are shorter: 2 h absolute, 30 min idle. Same Origin check, CSP and
  per-client throttle as the normal login. With `DEMO_MODE` off, `/api/auth/demo` is 404 and
  the buttons don't render.
- With `DEMO_ALLOW_KEY_SIGN_IN=false`, the paste-a-key form is hidden and the login route
  returns 404 in demo mode. The owner manages the demo server with the CLI over SSH, not
  through the public console.

### 3. The console in read-only mode

- When the session's role is `viewer`, show a persistent, polite banner: "Read-only demo.
  Changes are disabled; this is a live gateway with synthetic data." Mutating controls are
  shown **disabled with an explanation** (tooltip or inline text) rather than hidden, so
  visitors still see what the product can do.
- Defence in depth: the BFF rejects mutating requests for viewer sessions with 403 before
  calling the API. **The API remains the authority**; the BFF check only saves a round trip.
- Exports (CSV) and Cmd+K search work for viewers (they are reads).

### 4. Never real providers or real money

- The demo profile runs the gateway against the **fake provider** from `loadtest/` (no real
  provider keys exist on the server). It uses catalogued model names, as the load test does.
- Startup guard: in demo mode (a gateway setting such as `GATEWAY_DEMO_DEPLOYMENT=true`),
  the gateway **refuses to start** if any provider base URL points outside the compose
  network (i.e. at a real provider host). Test it.

### 5. Keeping the demo alive

- **Daily refresh:** a `demo-refresh` service runs the seeder once a day (e.g. 03:00 UTC)
  so charts always end "today". Viewers can't change data, so no destructive reset is
  needed. The seeder gets a flag (e.g. `GATEWAY_DEMO_SEED_SIGNIN_KEYS=0`) to **skip creating
  its admin sign-in keys** on the server: only the viewer keys exist there. The seeder's
  local-database check must accept the compose service name.
- **Live traffic (small):** a `demo-traffic` service sends a request through the gateway to
  the fake provider every ~60 s, with jitter, using a demo tenant key from a server-only
  secret file. Mix models and aliases, add occasional streaming, and every few minutes a
  request with a fake email so guardrail redaction shows up. Visitors then see "just now"
  rows in the Requests log. Keep the rate tiny.

### 6. Deployment kit (one VPS, Docker Compose, automatic HTTPS)

- A compose profile `demo` (or `deploy/demo/compose.yaml` if cleaner; justify the choice)
  with:
  - postgres, redis, gateway (admin API enabled), fake-provider, console (DEMO_MODE),
    demo-refresh, demo-traffic;
  - **Caddy** (pinned image) as the only service publishing ports (80/443), with automatic
    HTTPS for `${DEMO_DOMAIN}`, reverse-proxying to the console only.
  The gateway's public API, admin API, metrics, Postgres and Redis are reachable **only on
  the internal network**; nothing else is published.
- Caddy:
  - HSTS, compression, request-size limit, a sensible rate limit if Caddy supports it
    without a plugin (otherwise document a Cloudflare/firewall option);
  - it must **replace** any client-supplied X-Forwarded-For. Verify Caddy's documented
    behaviour and set `ADMIN_CONSOLE_TRUSTED_PROXY_HOPS=1` accordingly.
- Secrets: a `.env.demo.example` with placeholders only. A small script,
  `deploy/demo/bootstrap.sh`, run **on the server**:
  - generates the session secret, pepper and cache key;
  - migrates the database;
  - creates the viewer keys and the demo tenant key into a root-only env file;
  - seeds.
  It **never prints a secret**, and is idempotent.
- `docs/deployment-demo.md`, a runbook in plain language for a first-time deployer:
  - create an Ubuntu LTS VPS (e.g. Hetzner or DigitalOcean; ~€5-12/month);
  - SSH-key login only;
  - firewall allowing 22/80/443 only;
  - automatic security updates;
  - install Docker;
  - get the code onto the server (git clone after the repo is pushed, or rsync before);
  - point a DNS A record (e.g. `demo.udochukwu.cv`) at the server;
  - run the bootstrap and `docker compose ... up -d`;
  - update to a new version;
  - check health; rotate the viewer keys; take the demo down.
  Every command should be copy-pasteable, with an explanation of what it does.

## Tests required

- **Python:**
  - viewer matrix: every mutating route returns 403 `read_only_admin` with no side
    effects, no audit event and no idempotency record;
  - every allowed GET works for each viewer scope;
  - an org-scoped viewer can't see other orgs (404);
  - the completeness test fails if a new route lacks a viewer row;
  - the migration upgrade and its refusing downgrade;
  - CLI viewer key creation;
  - the gateway's demo-deployment guard rejects real provider hosts;
  - the seeder flag skips sign-in keys.
- **Console unit and component:**
  - demo-config validation;
  - the startup role check (a platform key is refused);
  - the demo route: 404 when off, Origin check, throttle;
  - the read-only banner and disabled controls with explanations;
  - the BFF rejects viewer mutations.
- **E2E (named tests) against a demo-mode stack:**
  - clicking each "Explore" button lands on the Overview with a viewer identity;
  - the demo tour as the platform viewer and the org viewer visits every screen;
  - direct mutation attempts (fetch to the BFF) return 403;
  - the paste-key form is absent in demo mode;
  - the no-leak scan confirms no `lgwa_`/`lgw_` value in any response, including the demo
    route.
- **Compose:** `docker compose --profile demo config` validates without real secrets (or
  equivalent for a separate file). If Docker image pulls or builds fail only for lack of
  network, say so; the reviewer will build and run it.
- **Break checks:**
  - (a) the viewer check is removed from the authorisation layer;
  - (b) the demo route returns the key in its body;
  - (c) startup accepts a platform-admin key as `DEMO_VIEWER_KEY`;
  - (d) the demo route is active with `DEMO_MODE` off;
  - (e) Caddy publishes the admin port.

## Docs

- **ADR 0028:** public demo mode:
  - a viewer role enforced by the API;
  - server-side demo sign-in with a role check at startup;
  - the fake provider only, with the guard;
  - daily refresh instead of reset;
  - a single-VPS deployment and its limits (no high availability; it's a demo).
- **`docs/architecture.md`:** a "Step 16" section in plain language:
  - read-only roles;
  - why the demo key never reaches the browser;
  - what a reverse proxy and automatic HTTPS are (analogy: a building's reception desk that
    checks everyone in and keeps the inner doors locked).
- **Threat model:** public exposure, demo vandalism, credential publication, cost abuse,
  denial of service, and scraping. For each, the mitigation and what remains.
- **README:** a "Live demo" section (URL placeholder until deployed) and the screenshots;
  **roadmap:** step 16.

## Out of scope

Real providers in the demo, visitor accounts or SSO, analytics or trackers on visitors (none,
for privacy), multi-server high availability, buying the domain or server (the owner does
that), and pushing to GitHub (done separately after a secret-history check).

## Report back with

- All gateway gates (ruff, format, pyright, pytest, db, redis) and console checks
  (format:check, lint, typecheck, unit, e2e with every test's name, build).
- The no-leak count, the break checks and the tests that caught them, the viewer matrix
  summary, the compose config validation output, open decisions, and
  `git log --oneline main..HEAD`.
