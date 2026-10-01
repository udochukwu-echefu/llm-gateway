# Step 15: Console completeness (request log, analytics, settings, and the small things)

- **Branch:** `feat/step-15-console-completeness` (from `main` at 5a55491; steps 13b and 14 are merged)
- **Read first:** `AGENTS.md`, `docs/architecture.md` (Steps 5, 7, 8, 10-14), ADRs 0022-0026 (0026 = Z.ai and NVIDIA providers),
  `docs/security/threat-model.md`, the step 13a/13b specs, this spec
- **Needs:** Docker (Postgres, Redis), Node 24.15.0. No new npm packages are expected; if
  one is truly needed, stop and report which and why.

## Goal

After 13b the console can do everything the admin API can. But compared with established
LLM gateway consoles (LiteLLM, Portkey, Helicone), an operator still can't answer everyday
questions:

- "Show me the failed requests from the Search team in the last hour."
- "Is Groq slow today? How often did we fall back?"
- "Which keys expire this week, and which were never used?"
- "What is this gateway configured to do?"

The gateway already records the answers: every provider-bound request stores its status,
outcome, latency, time to first byte, streaming flag, tokens, cost, cache result, redaction
count, alias, fallback and retry attempt. **It never stores prompts or responses, by design,
and this step must not change that.** This step exposes that metadata, adds a settings area,
adds the everyday conveniences (filters, sorting, search, export), and makes the demo data
cover every screen and state.

## Decisions already made (binding; object in your report if you disagree)

### 1. Requests log (the biggest gap)

- **Backend:** `GET /admin/v1/orgs/{org}/requests`: metadata rows from usage records,
  org-scoped (other orgs are 404), newest first, cursor-paginated (max page size 200), with
  filters:
  - time range (`since`/`until`, timestamps), team, key ID, provider, model, alias, endpoint;
  - status class (2xx/4xx/5xx) or exact status, outcome, cost status;
  - `stream`, `cache_hit`, `redacted` (redaction count > 0), `fallback` (fallback_from set),
    `retried` (attempt > 1);
  - minimum latency.
  Validate every filter strictly (unknown filter → 400). Add a migration with the index(es)
  the query plan needs (e.g. `(organization_id, created_at DESC)`); show `EXPLAIN` evidence in
  the report.
- **`GET /admin/v1/orgs/{org}/requests/{request_id}`:** all attempts for one request
  (retries and fallbacks, in order) for the detail view.
- **Console "Requests" page:**
  - a table with sortable columns;
  - a filter bar whose filters live in the URL (shareable links, back button works), with
    removable filter chips;
  - quick ranges (15m, 1h, 24h, 7d, 30d, custom);
  - a detail drawer showing the attempt timeline (e.g. "groq 502 → retry → deepseek 200");
  - copyable request ID;
  - "Export CSV" of the current filter, capped and streamed by the BFF (the cap is stated in
    the UI).
- A clear note in the UI: "Prompts and responses are never stored. This log is metadata only."

### 2. Analytics (performance and reliability)

- **Backend:** `GET /admin/v1/orgs/{org}/analytics`, or an extension of `/usage` if cleaner
  (justify the choice).
  - Measures, per time bucket (hour or day) and optional group (provider, model, team):
    request count, error rate, p50/p95/p99 duration and TTFB (Postgres `percentile_cont`),
    fallback count, retry count, cache-hit rate and savings, redaction count.
  - Say plainly in the docs that these are percentiles over recorded attempts, not the
    gateway-overhead SLO metric from step 12.
- **Console "Analytics" page:**
  - date-range picker (7/30/90 days, custom);
  - group-by switch;
  - charts with labelled axes, legends and table alternatives (the 13a standard);
  - unknown values shown as gaps, never zeros.

### 3. Settings

A **Settings** area with three sections:

- **Account** (everyone):
  - the signed-in admin's name, role, key ID and organisation;
  - session start, and absolute and idle expiry;
  - sign out.
- **Preferences** (everyone, stored in the browser, never on the server):
  - theme (light/dark/system, now **persisted**);
  - time display (UTC or local, with the zone always shown);
  - table density (comfortable/compact);
  - default landing page.
  Must work under the existing CSP: no inline scripts or `style` attributes.
- **Platform** (platform admins only; read-only):
  - **Backend:** `GET /admin/v1/settings`, platform-only. It returns an **allowlisted,
    non-secret** view of the effective configuration:
    - gateway version and git commit if known, catalogue version;
    - which providers are enabled and whether a key is configured (yes/no, never the key or
      its length);
    - provider base-URL hosts;
    - default limits, budget and alert threshold;
    - guardrail defaults; cache enabled and TTL; verified-key cache TTL;
    - Redis fail-open/closed mode; retry and circuit-breaker settings;
    - usage writer settings; whether metrics and tracing are enabled.
  - Test that no secret, pepper, database URL, Redis URL or key-shaped value can appear.
    Build the response from an explicit allowlist, not by dumping settings.
  - The UI explains that settings come from environment variables and change through a
    deploy, not through the console (twelve-factor config).

### 4. Providers and models

- **Console "Models" page:**
  - the catalogue: model, provider, host vs maker, region, endpoints, prices (effective now,
    with history), source link and checked date;
  - aliases with their targets and weights;
  - filters by provider, region and endpoint;
  - "Which teams can use this model?" for the current org (from the effective policies).
- **Provider health** (platform admins):
  - for each provider: enabled, and a recent error rate and p95 latency from usage records
    (last 15 minutes and 24 hours);
  - plus the circuit-breaker state **as seen by the replica serving the admin API**
    (`GET /admin/v1/providers`), clearly labelled "this replica", because breaker state is
    in-process per replica (ADR 0013).

### 5. Keys, teams and audit: the everyday conveniences

- **An org-wide "Keys" page** plus the team keys tab:
  - search by name or key ID;
  - status filter: active, expiring within 7 days, expired, revoked, never used;
  - team filter and sortable columns;
  - **last used** (backend: include `last_used_at` per key, from usage records) and
    "expiring soon" badges.
- **Teams list:** columns for spend this month, budget use %, key count, and last activity;
  sortable.
- **Audit log:**
  - filter by action (a dropdown of the known actions), actor, target type and a date range
    (from *and* to);
  - an event detail drawer (safe detail fields only);
  - CSV export of the current filter;
  - filters kept in the URL.

### 6. Global UX

- **Command palette / global search** (Cmd/Ctrl+K):
  - jump to an org, team or key by name or ID, or to any page;
  - platform admins search all orgs, org admins only their own.
- Breadcrumbs on every page.
- Relative times ("5 min ago") with the absolute time in a tooltip.
- Copy buttons for IDs.
- Toast confirmations for saves.
- A keyboard-shortcut help dialog (`?`).
- Proper 404 and error pages.
- Loading skeletons.
- Every table: sortable, with a visible "showing N of M" and cursor "load more".
- Filters and sorting in the URL wherever there is a list.
- Responsive down to phone width for read-only use (tables scroll horizontally inside their
  container; no page-level horizontal scroll).

### 6b. Findings from the step 13b review (fix in this step)

- **Budget states must be distinct.** On the Overview, a team spending $0.2685 of a $0.25
  budget shows a full green bar and "Above alert threshold", the same as a team at 81%.
  Show three states with text *and* colour (never colour alone): under the threshold;
  past the alert threshold (warning); **over budget** (danger, with "Requests are being
  refused" if the gateway enforces the budget).
- **Money display.** Amounts appear with inconsistent precision ("$0.94885675",
  "$0.28511", "$25.000000000001"). Display rule:
  - show 2 decimals, or up to 4 significant decimals for amounts under $0.01, rounded with
    BigInt decimal arithmetic (never floats);
  - the exact value in a tooltip, and in CSV exports;
  - budgets entered by admins show exactly as entered.
  Unit-test the rounding, including half-up cases and values like 0.000000000001.
- **Screenshots misrender long pages.** Full-page Playwright captures taken after scrolling
  draw the sticky sidebar halfway down the page and show the hidden "Skip to content"
  link (e.g. `docs/images/console-policies-team.png`). The live UI is correct; the capture
  method is not. Scroll to the top before capturing, and for pages taller than the
  viewport either capture the viewport plus named sections or add a screenshot-only style
  switch (a class set by the test, not a runtime feature) that makes the sidebar static.
  Check every screenshot in the set by eye.
- **The demo seeder doesn't check the database is local.** It says "for a local
  database" but only checks `GATEWAY_DEMO_SEED=1`. Refuse unless the database host is
  loopback or a compose-internal service name (`localhost`, `127.0.0.1`, `::1`,
  `postgres`), and test the refusal.

### 7. Demo data that covers every screen

Extend the step 13b seeder (`scripts/seed_demo.py`, still opt-in with `GATEWAY_DEMO_SEED=1`,
still refusing non-local databases, still idempotent, still no provider calls) so that
**every screen and every state** has data.

- **Organisations:** at least three, with distinct stories:
  - "Demo Co": a general SaaS company;
  - "Northwind Health": EU-only residency, strict guardrails, an org admin;
  - "Orbit Labs": a small, new org with little data, to show near-empty states.
- **Teams:** every limit source (override, default, unlimited), and every budget state (well
  under, past the alert threshold, exhausted).
- **Keys:** active, expiring within 7 days, expired, revoked and never used.
- **Policies:**
  - model policies at org and team level (exact models and provider wildcards), and one team
    set to "allow nothing" (a paused sandbox team);
  - guardrails using every action;
  - residency including `eu`, `sg` and `global`.
- **90 days of usage** across every catalogued provider and model (Groq, DeepSeek, Gemini,
  Z.ai, NVIDIA; OpenAI only if catalogued). It includes:
  - streaming and non-streaming requests;
  - 4xx and 5xx outcomes and incomplete streams;
  - retries and fallbacks, with realistic attempt chains sharing a request ID;
  - cache hits with savings, unpriced rows and redactions;
  - realistic latency distributions per provider, with a visible "Groq slow day" incident
    (the Analytics and Requests pages then tell a story).
- **Audit events** for every action type, produced through the real service so the hash
  chain verifies. Backdate only if the chain code supports explicit timestamps without
  weakening verification; otherwise say so.
- **Demo sign-in:**
  - The seeder creates a demo platform admin key and a demo org admin key (Northwind Health).
  - It writes them to a git-ignored file with mode 0600 (e.g. `.demo-keys.env`), **never
    prints them**, and replaces them on re-run by revoking the old ones.
- **A coverage checklist** in the README mapping each screen and state to the seeded data
  that shows it.
- **A demo tour test** (Playwright, run against a seeded stack):
  - visits every screen and tab as the platform admin and as the org admin;
  - asserts that no screen shows an empty state where the checklist promises data;
  - with `CONSOLE_SCREENSHOTS=1`, saves a full screenshot set (light, dark, tablet, phone) to
    `docs/images/console/`, used by the README and the portfolio.

## Security rules (unchanged from 13a/13b)

- The browser never sees admin keys or tenant keys.
- Every new endpoint gets an authorisation-matrix row, and org scoping is enforced in the
  API, never in the UI.
- Every new BFF route has a strict allowlist schema.
- CSV exports are generated server-side and pass through the same credential-redaction and
  no-leak scan.
- No prompts or responses are ever stored or shown.

## Tests required

- **Python:**
  - each new endpoint: shape, filters, validation (unknown filter → 400), pagination, and
    org isolation (404);
  - `/settings` never contains secret-shaped values (a negative test with a real-looking fake
    secret in the settings);
  - query-plan index usage evidence.
- **Unit and component:**
  - URL-synced filter state;
  - CSV escaping (including formula injection: cells starting with `=`, `+`, `-`, `@` are
    neutralised);
  - relative-time formatting;
  - preference storage;
  - command-palette scoping.
- **E2E (named tests):**
  - requests-log filtering and the detail drawer;
  - CSV export contents;
  - analytics range and group switches;
  - settings for platform vs org admin (the platform section is absent and its API returns
    403 for org admins);
  - keys search and status filters;
  - audit filters and the event drawer;
  - command palette;
  - the demo tour;
  - the no-leak scan across all of it.
- **Break checks:**
  - (a) `/settings` dumps the full settings object;
  - (e) the seeder's local-database check is removed;
  - (b) the requests endpoint drops the org filter;
  - (c) CSV cells are not neutralised;
  - (d) the command palette searches all orgs for an org admin.

## Docs

- **ADR 0027:** metadata-only request log, analytics percentiles, the read-only settings
  allowlist, and CSV safety.
- **`docs/architecture.md`:** a "Step 15" section in plain language:
  - why we log metadata but never prompts;
  - what a percentile over attempts means;
  - why settings are read-only (configuration as code).
- **Threat model:** CSV injection, settings disclosure, cross-org search.
- **README:** new screenshots and the demo coverage checklist. **Roadmap:** step 15.

## Out of scope (later)

Webhooks and email notifications for budget alerts, SSO and user invitations, admin-key
management from the UI (kept CLI-only on purpose), a prompt playground, storing request
content, editing configuration from the UI, a public hosted demo mode.

## Report back with

- All gateway gates (ruff, format, pyright, pytest, db, redis) and console checks
  (format:check, lint, typecheck, unit, e2e with every test's name, build).
- The no-leak count, the break checks and the tests that caught them, the EXPLAIN evidence,
  the screenshot set's paths, the demo coverage checklist, open decisions, and
  `git log --oneline main..HEAD`.
