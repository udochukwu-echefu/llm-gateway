# Step 13a: Admin console (web UI), core management

- **Branch:** `feat/step-13a-admin-console` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs (especially 0022, the admin
  API), `docs/security/threat-model.md`, `README.md` (admin API section), this spec
- **Needs:** Docker running (Postgres and Redis), Node.js LTS

## Goal

Step 12a exposed every management operation over a private admin HTTP API. Nobody
should have to use `curl` to run a company's gateway. This step adds a **web console**
where platform and org admins log in and manage the gateway by clicking.

13a covers the core: sign-in, organisations and teams, API keys, limits and budgets, a
usage overview, and the audit log. Step 13b adds editors for model policies,
guardrails, residency and cache purge, which completes the console.

## Decisions already made (binding; object in your report if you disagree)

### 1. Stack and location

- A **Next.js** app (App Router, current stable version) with **TypeScript in strict
  mode** and **Tailwind CSS**, in `admin-console/` at the repo root. Use npm with a
  committed lockfile, and pin the Node version (`.nvmrc` and `engines`).
- Keep dependencies few and well known. Allowed: `next`, `react`, `react-dom`,
  `tailwindcss`, `iron-session` (encrypted session cookie), `zod` (validation), and a
  small chart library for the usage view (e.g. `recharts`). Tests: `vitest`,
  `@testing-library/react`, `@playwright/test`. Justify anything else in the report.
- Code organisation follows the spirit of AGENTS.md: small single-purpose modules,
  `app/` for routes, `lib/` for the admin API client, session and validation, and
  `components/` for UI. No catch-all `utils.ts`.

### 2. Backend for frontend: the browser never sees the admin key

- **Sign-in:** the admin pastes their `lgwa_…` key into a login form. The Next.js server
  validates it by calling the admin API, then stores it inside an **encrypted,
  httpOnly, Secure, SameSite=Strict** session cookie (`iron-session`, with a secret of
  at least 32 bytes from the environment, `ADMIN_CONSOLE_SESSION_SECRET`). Browser
  JavaScript can't read the cookie, and it's unreadable without the server secret.
- **Every** admin API call is made **server-side** (route handlers, server actions or
  server components) to `ADMIN_API_URL` (e.g. `http://127.0.0.1:8081`), which is never
  exposed to the browser. The admin key never appears in HTML, the JS bundle, client
  components' props, or any response to the browser.
- Sessions: 8 h absolute and 30 min idle expiry. Logout destroys the session. If the
  admin API returns 401 (e.g. the key was revoked), destroy the session and redirect to
  login.
- **CSRF:** SameSite=Strict, plus an explicit `Origin` check on every mutating request
  (server actions already check origin; document how). Test it.
- **Security headers:** a strict Content-Security-Policy with per-request nonces (no
  `unsafe-inline` scripts), `frame-ancestors 'none'`, `Referrer-Policy: no-referrer`,
  and `X-Content-Type-Options: nosniff`.
- The UI adapts to the role (platform vs org admin), but **the admin API remains the only
  authority**. Hiding a button is convenience, not security, and the BFF must never add
  privileges or rewrite org scopes.
- Creations send an `Idempotency-Key`, generated once per form submission, so a
  double-click or retry never creates two keys or teams (this reuses step 12a).

### 3. A small backend addition: "who am I"

- Add `GET /admin/v1/me` to the gateway's admin API. It returns the calling admin key's
  `key_id`, `name`, `role` and `organization` (for org admins). It's Python, in the
  existing `admin/api` package, with tests and a row in the authorisation matrix (the
  completeness test must cover it). The console uses it after login to decide what to
  show.

### 4. Screens (13a)

- **Sign in / sign out.**
- **Organisations** (platform: all, with create; org admin: redirected to their own org).
- **Organisation page:** a teams list (create team), plus a usage overview for the
  current month (spend per team vs budget, top models, requests and tokens over time,
  cache savings, and **unpriced usage shown explicitly, never as zero**). Money is
  displayed from the API's decimal strings; never parse money into a JS float for maths.
- **Team page, tabs:**
  - *API keys:* list (key ID, name, status, created, expiry), **create** (the full key
    is shown **once** in a dialog with a copy button and a clear "you won't see this
    again" warning; after closing, it's gone and can't be recovered), and **revoke**
    (with a confirmation dialog that names the key ID).
  - *Limits:* show overrides vs effective values with their source (override, default or
    unlimited); edit RPM, TPM and max concurrency; clear overrides.
  - *Budget:* show spend vs budget with a progress bar and the alert threshold; edit
    the budget and threshold.
- **Audit log:** paginated with the API's cursors, filterable by action and date. Show
  actor, action, target and time. Platform admins get a **"Verify chain"** button that
  calls `/audit/verify` and shows the result.
- Every API error is shown in plain words, using the error envelope's message. Another
  org's resource surfaces as "not found", which is what the API says.

### 5. Design and accessibility

- Clean, calm and professional: an operations tool, not a marketing site. A consistent
  spacing and type scale, and light and dark themes.
- Accessible: keyboard navigation everywhere, visible focus states, labelled form
  fields, dialogs that trap focus and close on Escape, WCAG AA contrast, and semantic
  tables.
- Responsive down to tablet width. Loading, empty and error states for every data view.

### 6. Running it

- `admin-console/Dockerfile` (multi-stage, non-root) and a compose profile `console`
  running the console plus the gateway with the admin API enabled.
- The console's settings come from environment variables, validated at startup with
  `zod` (fail fast, like the gateway).

## Tests required

1. **Unit (Vitest):** the session helpers (encryption round trip, expiry, a tampered
   cookie is rejected), the admin API client's error mapping, money formatting from
   strings, and the idempotency-key-per-submission behaviour.
2. **Component tests:** the key-created dialog shows the key once and has no way to
   reveal it again; the revoke dialog requires confirmation; forms validate input.
3. **End-to-end (Playwright)** against the real stack (gateway with the admin API,
   Postgres, Redis, the console):
   - log in as a platform admin → create an org and team → create a key (shown once;
     reloading doesn't show it again) → set limits and a budget → revoke the key → see
     all of these in the audit log → "Verify chain" passes;
   - log in as an org admin → can't see or reach another org (URL tampering shows "not
     found");
   - **no leak:** record every response the browser receives during the whole run, and
     assert that no admin key (`lgwa_…`) and no created tenant key after its one-time
     dialog appear anywhere in HTML, JS, JSON or headers;
   - the session cookie is httpOnly (`document.cookie` can't see it); a cross-origin
     POST to a mutating route is rejected; the CSP header is present, with a nonce.
4. The gateway's `GET /admin/v1/me` is tested in the Python suite and in the
   authorisation matrix.
5. Before reporting, temporarily break each of these and confirm a test fails: (a) pass
   the admin key to a client component, (b) drop the Origin check, (c) make the
   key-created dialog re-openable, (d) remove `httpOnly` from the session cookie.

## Docs and CI

- **ADR 0024:** the admin console architecture (BFF, encrypted session cookie, CSRF
  defences, CSP, the API as the only authority).
- **`docs/architecture.md`:** a "Step 13a" section in plain language: what a BFF is and
  why the browser must never hold the admin key (analogy: a bank teller handles the
  vault key, the customer never touches it), plus what CSRF, XSS and CSP are.
- **Threat model:** session theft, XSS, CSRF, clickjacking, the admin key reaching the
  browser, and UI-only authorisation.
- **README:** running the console locally, and a few screenshots in `docs/images/`.
- **`AGENTS.md`:** add the console's commands (install, lint, typecheck, unit, e2e,
  build) and a short "Frontend" code-organisation note.
- **CI:** a job for the console (install, lint, typecheck, unit tests, build). Run e2e in
  CI with compose services if feasible, otherwise document how to run it locally.

## Out of scope (step 13b or later)

Editors for model policy, guardrails and residency; cache purge; SSO/OAuth; managing
admin keys from the UI; multi-language UI.

## Report back with

- Final output of the gateway gates (ruff, format, pyright, pytest, db, redis) and the
  console checks (lint, typecheck, unit, e2e, build).
- Screenshots of the main screens (paths in the repo).
- The e2e no-leak test's result (number of responses scanned).
- Design as built, open decisions, dependencies added, and `git log --oneline main..HEAD`.
