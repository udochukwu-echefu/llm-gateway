# Public demo: one portable appliance on InstaCloud

This is a **synthetic, read-only portfolio demo**, not a production service.
The owner executed the initial provisioning/deployment once on **2026-10-01** and
confirmed it working at
[the live platform URL](https://prod-main-appliance-ca05b3-00hcr9bqd1b.compute.instacloud-edge.com). Run exactly **one appliance instance**. Console, gateway and fake
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
**The initial install/setup, three services, bindings, secrets, staged source deployment
and visitor verification were executed once by the owner on 2026-10-01 and worked.**
The npm-prefix fallback and `agent setup --create` command below record that owner
evidence alongside the references. Custom-domain changes, rollback, paid scaling and
resource removal remain documentation-verified only, not owner-executed. No platform
commands or deployments were run while implementing step 16b. Check installed CLI help;
APIs and plan limits can change. Never
bypass governance by switching to human mode: relay an approval requirement to the owner [G].

## 1. Install, log in and create resources [S, C]

On the owner's deployment machine (not an offline test sandbox), with Node installed:

```bash
npm install -g insta
# If the global npm prefix is system-owned, use this writable prefix instead:
npm install -g insta --prefix "$HOME/.npm-global"
export PATH="$HOME/.npm-global/bin:$PATH"
insta --agent login
insta --agent status --json
insta --agent agent setup --create llm-gateway-demo -y
insta --agent service add postgres db --pg-version 17
insta --agent service add redis cache
insta --agent service add compute appliance --port 3000 --no-always-on
insta --agent service list --json
```

The fallback bin path is `$HOME/.npm-global/bin/insta`; keep that directory on PATH.
Do not use sudo or `--force`. Setup creates/links the project and installs local tooling;
keep `.insta/`, `.claude/` and `.codex/` on this machine and out of Git. This project is
already provisioned: do not repeat setup or service creation for routine updates.
`service add compute` prints the public platform URL: save it for the Origin setting
and verification before attaching a custom domain.

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
DEMO_URL=https://prod-main-appliance-ca05b3-00hcr9bqd1b.compute.instacloud-edge.com
insta --agent secrets set ADMIN_CONSOLE_ORIGIN "$DEMO_URL" --service compute/appliance
insta --agent secrets set ADMIN_CONSOLE_TRUSTED_PROXY_HOPS 0 --service compute/appliance
```

Set `ADMIN_CONSOLE_ORIGIN` to the exact URL printed when compute was created **first**.
The value shown above is the owner's current platform URL; a new project has a different one.
Switch to a custom domain later; allow only one origin at a time.

The repository helper generates pepper, standard-base64 AES-256 cache key and session
secret **locally**,
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

From the repository root, commit the reviewed changes, then run the helper:

```bash
./deploy/demo/stage.sh
insta --agent compute status appliance --json
```

The helper refuses a dirty working tree, including non-ignored untracked files. It runs
`git archive HEAD` into a fresh temporary directory, then copies the **archived**
`deploy/demo/Dockerfile` to that directory's root. Ignored `.env`, `.demo-keys.env`,
`.insta/` and agent folders never enter the context. Do not commit secret files.
The helper runs these source commands [D, C] and leaves the deployment URL visible:

```bash
insta --agent build <staged-directory> --port 3000
insta --agent deploy <staged-directory> --group appliance --port 3000
```

`<staged-directory>` is supplied by the helper, not a path to paste literally. It removes
the temporary context on success or failure. The local CLI still resolves the project
binding from the repository; the binding itself is never uploaded. The Dockerfile has
pinned Python 3.13.12, Node 24.15.0 and uv 0.11.0 bases and supports native amd64/arm64
builds. EXPOSE, listen PORT and `--port` must all equal **3000**. Another injected PORT
fails clearly. No privileged container or persistent volume is needed. Record `git rev-parse HEAD` as the release and retain a compatible previous commit for rollback.

New compute starts with one instance. **Verify one in status/manifest** and never scale out.
On a paid plan, `insta --agent compute scale 1 appliance` explicitly sets it [C]; that
command is paid-only and is not needed for a default free single-instance service. Reject
deployment if status shows more than one. Two briefly overlapping rollouts are safe because
boot revocation touches only appliance keys older than 24 hours, never the new boot's keys.

Each wake waits for dependencies (30 s bound), migrates under a Postgres advisory lock,
appends only missing synthetic days, starts loopback services, creates boot-ID viewer and
tenant keys through a private memory pipe, checks viewer roles, then starts console and traffic.
Child stdout/stderr streams through the supervisor line by line with a child-name prefix,
for example `[gateway]`. Key-shaped strings and credential-bearing Postgres/Redis URLs
are redacted before printing. Final crash diagnostics are drained before the supervisor
reports the child exit. This is defence in depth; application logs still contain metadata only.
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
it to the custom origin when switching. The console intentionally allows only one Origin:

```bash
insta --agent secrets set ADMIN_CONSOLE_ORIGIN https://demo.udochukwu.cv --service compute/appliance
```

## 5. Verify, update, roll back and take down [D, O, C]

```bash
DEMO_URL=https://prod-main-appliance-ca05b3-00hcr9bqd1b.compute.instacloud-edge.com
# A sleeping container may need more than one attempt. Poll for at most 60 seconds.
deadline=$((SECONDS + 60))
status=000
while (( SECONDS < deadline )); do
  status=$(curl --max-time 10 -s -o /dev/null -w '%{http_code}' "$DEMO_URL/login") || status=000
  [[ "$status" == 200 ]] && break
  sleep 3
done
[[ "$status" == 200 ]] || { echo "Demo did not return HTTP 200; inspect logs." >&2; exit 1; }
insta --agent compute status appliance --json
insta --agent agent manifest --json
insta --agent compute logs appliance --since 30m
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

Update from a clean, reviewed commit by running `./deploy/demo/stage.sh` again. For
rollback, switch to a clean branch at the recorded compatible previous commit and stage
that committed source. The example below requires a rollback commit that already contains
the helper; releases before step 16b need a separately reviewed staging procedure. No registry publication
is required [D].

```bash
# Routine update after committing the reviewed changes:
./deploy/demo/stage.sh
# Rollback to a recorded compatible commit that includes stage.sh:
git switch -c rollback/demo-release PREVIOUS_COMMIT
./deploy/demo/stage.sh
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
cd admin-console
CONSOLE_TEST_PORT=3300 npm run test:e2e:demo
```

From the repository root, `uv run python -m deploy.demo.measure` measures first provision,
then a cold process restart against the already-running seeded Postgres, waits 65 seconds
for a steady whole-container memory sample, reports local image size, and removes only
the disposable profile. Do not run it at the same time as the demo e2e profile.

The e2e runner rebuilds missing/stale images using its revision guard, then starts and
removes only this profile, including its disposable volumes.
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
docker build -f deploy/demo/Dockerfile -t llm-gateway-demo:docker-host .
docker run -d --name gateway-demo --env-file demo-runtime.env --stop-timeout 25 --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:3300:3000 llm-gateway-demo:docker-host
docker stop --time 25 gateway-demo
```

On a public host put a separately reviewed HTTPS proxy in front of the loopback mapping;
port 3000 is the only application port it should reach. Do not publish admin/metrics/API
ports or reuse this synthetic appliance for production. Portability does not supply TLS,
firewall rules, backups or platform abuse protection for an unmanaged host.
