# Public demo: one portable appliance on InstaCloud

This is a **synthetic, read-only portfolio demo**, not a production service. The live URL
is not deployed yet. Run exactly **one appliance instance**. Console, gateway and fake
provider share one container because InstaCloud documents no private networking between
web services; separate web services would each have a public URL. Only console port 3000
is routed. Public API 18090, admin 18091, metrics 19464 and fake provider 18000 bind loopback.
The platform handles HTTPS; there is no Caddy, public cron hook or persistent boot-key file.

## Sources and verification limits

Official InsForge/InstaCloud references (read 2026-10-01):

- [S: setup/install/login/project](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/setup.md)
- [D: deploy/PORT/bindings/domain/DNS](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/deploy.md)
- [O: operate/cold starts/status/recovery](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/operate.md)
- [C: CLI catalog/secrets stdin/scale/remove](https://github.com/InsForge/instacloud-skills/blob/main/insta/cli-reference.md)
- [G: governance/approvals](https://github.com/InsForge/instacloud-skills/blob/main/insta/references/governance.md)

Source letters next to command blocks cite every InstaCloud command in that block.
**All platform commands below are documentation-verified only, not executed against an
account.** No resources, login, billable deployment, registry push or DNS change was made
during implementation. Check installed CLI help; APIs and plan limits can change. Never
bypass governance by switching to human mode: relay an approval requirement to the owner [G].

## 1. Install, log in and create resources [S, C]

On the owner's deployment machine (not an offline test sandbox), with Node installed:

```bash
npx -y insta@latest --agent agent setup
insta --agent login
insta --agent status --json
insta --agent project create llm-gateway-demo
insta --agent agent setup
insta --agent service add postgres db --pg-version 17
insta --agent service add redis cache
insta --agent service add compute appliance --port 3000 --no-always-on
insta --agent service list --json
```

Login opens a browser approval page; use `insta --agent login --device` on a headless
machine [S]. Confirm the linked project/branch before every mutation. Creating compute
without `--no-always-on` defaults to always-on. No production database belongs in this project.
Managed Postgres is reachable with credentials on 5432: retain the strong generated
password and TLS options in its binding. Redis is private. Restrict account access and
take managed backups. Only synthetic metadata and HMAC key hashes belong in Postgres.
This credential-reachable database is an accepted **demo-only** risk, not a production design.

## 2. Bind dependencies and generate secrets without printing them [D, C]

```bash
insta --agent secrets bind DATABASE_URL postgres/db --to compute/appliance
insta --agent secrets bind REDIS_URL redis/cache --source-name REDIS_URL --to compute/appliance
insta --agent secrets bindings --target compute/appliance
uv run python -m deploy.demo.set_secrets
insta --agent secrets set ADMIN_CONSOLE_ORIGIN https://demo.udochukwu.cv --service compute/appliance
insta --agent secrets set ADMIN_CONSOLE_TRUSTED_PROXY_HOPS 0 --service compute/appliance
insta --agent secrets list --json
```

The repository helper generates pepper, AES-256 cache key and session secret **locally**,
then calls the documented `secrets set NAME --service compute/appliance` stdin interface
[C]. Values never enter arguments, terminal output or files. It is an explicit initial
provision/rotation operation, **not** idempotent: do not rerun casually. Failure may leave
some names set; fix authentication/governance, then rerun before deployment. There is no
new package dependency. CLI versions >=0.0.78 redeploy recipients when secrets change [D/C].
Never use `secrets --print`, `secrets --json`, `postgres url`, shell tracing or `printenv`:
those can print plaintext. No real provider key or developer `.env` goes into this image.

Forwarded-IP trust stays **zero** because the retrieved docs do not establish the router's
chain replacement/append behavior. That may share the login quota across visitors behind
the platform proxy. Only enable a hop count after verifying the actual topology and that
direct origin access is blocked; arbitrary incoming X-Forwarded-For must not be trusted.
Platform DDoS/rate/body-size controls and HTTPS response headers need owner verification;
we do not claim an unverified platform WAF, HSTS or request-size limit. CSP/Origin/session
defenses remain in the console itself. Reads/CSV/audit verification consume resources.

## 3. Build and deploy [D, C]

Use the repository root as build context, not `deploy/demo/`. The Dockerfile has pinned
Python 3.13.12, Node 24.15.0 and uv 0.11.0 bases and native standalone/venv builds.
Both native `linux/amd64` and `linux/arm64` are supported. On an authorized publishing machine:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -f deploy/demo/Dockerfile -t REGISTRY/llm-gateway-demo:RELEASE --push .
insta --agent deploy --image REGISTRY/llm-gateway-demo@sha256:RELEASE_DIGEST --group appliance --port 3000
insta --agent compute status appliance --json
```

Replace the registry/release/digest placeholders; no publication is performed by this task.
Deploy an immutable manifest digest and save the previous digest for rollback. EXPOSE,
listen PORT and `--port` must all equal **3000**; another injected PORT fails clearly rather
than silently routing to the wrong socket. No privileged container or persistent volume is needed.

New compute starts with one instance. **Verify one in status/manifest** and never scale out.
On a paid plan, `insta --agent compute scale 1 appliance` explicitly sets it [C]; that
command is paid-only and is not needed for a default free single-instance service. Reject
deployment if status shows more than one. Two briefly overlapping rollouts are safe because
boot revocation touches only appliance keys older than 24 hours, never the new boot's keys.

Each wake waits for dependencies (30 s bound), migrates under a Postgres advisory lock,
appends only missing synthetic days, starts loopback services, creates boot-ID viewer and
tenant keys through a private memory pipe, checks viewer roles, then starts console and traffic.
Child stdout/stderr is discarded; the supervisor emits only safe readiness/failure messages.
Any child death fails the container. SIGTERM stops traffic/console, allows gateway usage
flush, then stops the fake provider under a 20-second shared budget; allow 25 seconds at the host.

**Migration caveat:** InstaCloud normally recommends separate expand/contract migrations
[D]. The owner explicitly chose startup migration for this portable demo. Locks and timeouts
prevent concurrent/hung boot, not backward-incompatible schema changes. Review migration
compatibility before updates; a failed boot must never be treated as a healthy deploy.

## 4. Attach the owner's custom domain [D, C]

```bash
insta --agent domain attach demo.udochukwu.cv --group appliance
insta --agent domain check demo.udochukwu.cv --group appliance
```

At the owner's existing DNS provider, create the **exact routing CNAME and validation
record printed by attach**. Their target/token is account-specific: do not invent an IP
or copy a placeholder record. No nameserver transfer or domain purchase is needed. Wait
for DNS/certificate status to be active, then verify HTTPS. If using the default platform
URL first, set `ADMIN_CONSOLE_ORIGIN` to that exact HTTPS origin [C], verify, then change
it to the custom origin when switching. The console intentionally allows only one Origin.

## 5. Verify, update, roll back and take down [D, O, C]

```bash
curl --max-time 60 -s -o /dev/null -w '%{http_code}\n' https://demo.udochukwu.cv/login
insta --agent compute status appliance --json
insta --agent agent manifest --json
insta --agent compute logs appliance --since 10m
```

Expect HTTP 200, both Explore buttons, Overview viewer identity/read-only banner,
disabled mutation controls, readable requests/analytics, working CSV/search, and no
paste-key form. `/admin/v1/me` on the public origin must not serve the gateway admin API
(an unauthenticated console request redirects to login HTML, not admin JSON).
Check the platform's routed port list: **only 3000**. Sleep after five minutes without
inbound router traffic, then visit again: cold start can take seconds. Frequent external
health pings prevent sleeping; do not schedule cron to keep this demo awake. Internal
traffic (three startup requests, then 50–70 s jitter) never reaches the inbound router.
History is topped up on wake, not continuously at midnight while asleep.

Update by deploying a new digest; rollback by redeploying the last compatible digest:

```bash
insta --agent deploy --image REGISTRY/llm-gateway-demo@sha256:NEW_DIGEST --group appliance --port 3000
insta --agent deploy --image REGISTRY/llm-gateway-demo@sha256:PREVIOUS_DIGEST --group appliance --port 3000
```

Run the verification above after either action. Rollback changes code, **not database
schema/data**. Never automatically downgrade migration 0012: it refuses existing viewer
rows, including revoked ones. Inspect the migration ledger after any interrupted boot;
recover deliberately, not by repeatedly deploying a known broken migration.

Boot keys rotate automatically on wake/restart, without ever displaying them. To trigger
rotation on a running service: `insta --agent compute restart appliance` [O/C]; for a
deliberately stopped service use `insta --agent compute start appliance` [O/C]. Old keys
remain usable until they age past 24 h and another boot revokes them; stolen encrypted
cookies remain replayable until session expiry. Pepper rotation invalidates every key;
cache-key rotation invalidates encrypted cached data; session-secret rotation logs visitors
out. Plan these separately, not as a routine image update. History/audit/revoked metadata
grow; monitor storage and adopt separately reviewed retention. No high availability is claimed.

Take the demo offline (retains data), or explicitly remove resources (destroys data):

```bash
insta --agent compute stop appliance
# Only after owner approval/backups:
insta --agent domain detach demo.udochukwu.cv --group appliance
insta --agent service remove compute appliance
insta --agent service remove redis cache
insta --agent service remove postgres db
```

Remove the demo routing/validation DNS records at the owner's DNS provider. Do not delete
the whole project or unrelated resources as a shortcut. Approvals and billing policy
still apply [G].

## Local test and measurements (no managed resources)

The standalone Compose file is **local test only**, with disposable Postgres/Redis and
synthetic placeholders. It publishes only `127.0.0.1:3300:3000`; it never touches the
owner's `gateway` database or ports 8000/8081/9464/3100. Run after Python db/Redis tests:

```bash
docker compose -f deploy/demo/compose.yaml --profile demo-test config --quiet
docker build -f deploy/demo/Dockerfile -t llm-gateway-demo:step16 .
cd admin-console
CONSOLE_TEST_PORT=3300 ./node_modules/.bin/playwright test -c playwright.demo.config.ts
```

From the repository root, `uv run python -m deploy.demo.measure` measures first provision,
then a cold process restart against the already-running seeded Postgres, waits 65 seconds
for a steady whole-container memory sample, reports local image size, and removes only
the disposable profile. Do not run it at the same time as the demo e2e profile.

The e2e runner starts and removes only this profile, including its disposable volumes.
No boot keys are extracted to a host state file; the shared scan rejects all admin/tenant
credential patterns in every browser response. Measurements and gate evidence belong in
`docs/tasks/step-16-report.md`. Cold start target is <=10 s from container start to HTTP
200 with Postgres already running; steady **whole-container** memory target <=1 GB. First
provisioning (migration plus full 90-day seed) is reported separately from an existing-DB
cold process start. Local Docker results do not promise platform router/database latency.

## Run the same image on any Docker host

Provide your own Postgres and Redis endpoints and a private mode-0600 `demo-runtime.env`
containing DATABASE_URL, REDIS_URL, pepper, cache key, session secret, exact console origin
and PORT=3000 (see `.env.demo.example` for placeholders). **Never put boot keys in that file.**
Use strong randomly generated values, ignore the file, and do not print it. Then:

```bash
docker run -d --name gateway-demo --env-file demo-runtime.env --stop-timeout 25 --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:3300:3000 REGISTRY/llm-gateway-demo@sha256:RELEASE_DIGEST
docker stop --time 25 gateway-demo
```

On a public host put a separately reviewed HTTPS proxy in front of the loopback mapping;
port 3000 is the only application port it should reach. Do not publish admin/metrics/API
ports or reuse this synthetic appliance for production. Portability does not supply TLS,
firewall rules, backups or platform abuse protection for an unmanaged host.
