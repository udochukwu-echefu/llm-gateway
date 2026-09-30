# Step 13a implementation and validation report

Date: 2026-09-30. Branch: `feat/step-13a-admin-console`.

## Built

`GET /admin/v1/me` returns verified public identity (key ID, name, role and
optional organization ID/name). It has Python endpoint tests and an authorization
matrix row. The console includes sign-in/out, organizations, team creation, monthly
usage, API key creation/revocation, limits, budgets and the paginated audit log with
filters and platform chain verification. ADR 0023 records the credential boundary.

The Next.js BFF makes all private admin calls server-side. It seals credentials in
an encrypted Secure/httpOnly/Strict host cookie, enforces 8-hour absolute and
30-minute idle expiry, clears sessions on logout/upstream 401, checks the configured
Origin on every mutation and supplies per-request nonce CSP. The gateway decides
permissions and organization scope. Creation requests retain one idempotency UUID
through double-clicks/retries. A tenant key exists only in its initial creation
response and the open dialog's component state.

## Gateway gates

These are the final successful outputs. Database and Redis invocations ran
**sequentially**, before browser tests, against Docker Compose Postgres and Redis.
The repository's installed `.venv` executables avoid sandbox cache restrictions.

| Gate / command | Final output |
| --- | --- |
| `.venv/bin/ruff check --no-cache .` | `All checks passed!` |
| `.venv/bin/ruff format --no-cache --check .` | `343 files already formatted` |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/pytest -p no:cacheprovider -q` | `1012 passed, 158 skipped, 25 deselected in 20.56s` |
| Same pytest invocation with `-m db`, database environment set | `94 passed, 10 skipped, 1091 deselected in 28.44s` |
| Same pytest invocation with `-m redis`, database and Redis environment set | `64 passed, 1131 deselected in 52.35s` |

The Python e2e harness was also explicitly checked with pyright: zero errors.

## Console checks

Run from `admin-console/` using the already installed pinned dependencies and Chromium.

| Command | Result |
| --- | --- |
| `npm run lint` | Exit 0; ESLint reported no diagnostics |
| `npm run typecheck` | Exit 0; `tsc --noEmit` reported no diagnostics |
| `npm test` | `Test Files 6 passed (6)` / `Tests 26 passed (26)` |
| `npm run test:e2e` | `1 passed (8.6s)`; also passed three consecutive scanner stability runs |
| `npm run build` | Exit 0; production Next.js 16.3.7 build succeeded; dynamic routes and Proxy |
| `npm run test:break` | All four mutations caught; sources restored; clean production build regenerated |

The e2e suite uses the real gateway admin server, a unique migrated disposable
Postgres database, Redis, production standalone Next.js and installed Playwright
Chromium. It ignores `.env`, creates fake-only identities and usage, and contacts no
model provider. It checks the full platform workflow, organization isolation, revoked
admin logout, cursor pagination/filtering/chain verification, exact budget display,
unpriced usage, dialog keyboard behavior, CSP and browser cookie flags.

**No-leak scan: 201 browser responses; one permitted key-creation response;
zero leaks.** Every browser response is matched to captured complete body/header
bytes. Bodies are captured before navigation can evict them; redirected responses
have an immediate fallback capture. Captured requests cancelled during navigation
are also scanned. No traces, videos or full-key dialog screenshots are retained.

## Deliberate break checks

All are temporary mutations of actual production source. The runner requires the
specific designated test to fail, then restores the original bytes even on error.

| Mutation | Test that caught it |
| --- | --- |
| Pass admin key to client Shell props | Playwright `real admin workflows, isolation, browser security and no-leak scan`; assertion `Admin credential in response` |
| Remove the Origin check | Vitest `mutating HTTP handlers reject cross-origin and missing Origin before any mutation` |
| Add retained secret and a Reveal key again control | Component test `the created key cannot be reopened after closing` |
| Remove cookie `httpOnly` | Session unit test `round trip encrypts the credential and has secure cookie flags` |

The final clean unit suite passed after restoration. No deliberate vulnerability remains.
Playwright explicitly sends SIGTERM to the Python harness so its cleanup runs.
After the final browser run and mutation checks, the disposable-database count was
zero and the ignored fake-credential state file was absent. Earlier abandoned test
fixtures were removed only after confirming they had no active connections.

## Screenshots

Synthetic data and public identifiers only; generated in the normal e2e run and
visually inspected. Dark and tablet views were also checked in the browser workflow.

- `docs/images/console-login.png`
- `docs/images/console-organisations.png`
- `docs/images/console-usage.png`
- `docs/images/console-keys.png`
- `docs/images/console-limits.png`
- `docs/images/console-budget.png`
- `docs/images/console-audit.png`
- `docs/images/console-usage-dark.png`
- `docs/images/console-tablet.png`

## Design and choices

A calm operations shell uses system fonts, semantic tables, labelled forms, visible
focus, responsive layouts and light/dark/system themes. Native dialogs trap focus,
restore focus and close on Escape. Theme selection lasts for the current document;
the default follows the OS. Small native SVG charts and token tables keep the usage
view readable. Recharts remains pinned in the prepared manifest but is unused.
Money uses exact BigInt pico-dollar arithmetic from decimal strings, including
Python Decimal exponent notation. Unknown costs remain explicitly unpriced. Monthly
boundaries use UTC; usage pages are exhausted before totals/rankings are shown.

Route handlers were chosen over Server Actions. `ADMIN_CONSOLE_ORIGIN` provides the
explicit trusted Origin, independently of forwarded/Host headers. Startup zod
validation covers this URL, the private API URL and the session secret. Names cannot
contain slash or be dot traversal; other punctuation and Unicode are encoded without
changing scope. Organizations in `/me` include both ID and name; platform identity has
null organization. No source module exceeds 400 lines; larger declarative screen
functions primarily contain JSX, with operations split into named modules.

The spec requested ADR 0023 although `0023-controlled-load-testing.md` already exists.
Both decisions are preserved; owner renumbering is the only documentation decision
left open. No binding architecture decision was changed. Step 13b features remain out
of scope. Stateless encrypted-cookie logout cannot revoke stolen ciphertext; revoking
the underlying admin key invalidates its use, as documented in the threat model.

## Dependencies

The first implementation commit records the prepared manifest, lockfile, `.nvmrc`
and `.gitignore`. No additional package was installed or version changed.

Approved additions beyond the original spec: `typescript`, `@types/node`,
`@types/react`, `@types/react-dom`, `eslint`, `eslint-config-next`,
`@tailwindcss/postcss`, `postcss`, `jsdom`, `@vitejs/plugin-react`,
`@testing-library/dom`, `@testing-library/user-event`. They provide strict typing,
Next lint rules, Tailwind 4 integration and DOM interaction/component testing.
TypeScript stays **5.9.3** and ESLint **9.39.5** for the specified plugin compatibility;
Node stays **24.15.0**. Vite 8 uses built-in `resolve.tsconfigPaths: true`;
`vite-tsconfig-paths` was not added. Next's existing `server-only` compiler marker
requires no new dependency.

## Container and CI limits

The multi-stage console Dockerfile runs non-root as UID 1001. The compose `console`
profile starts the gateway's private admin listener and the console, with only
loopback browser/public-model ports published. Compose configuration validation
passed. Docker socket access initially failed inside the sandbox; an approved Docker
invocation successfully started Postgres and Redis.

The attempted image build was:

```text
docker build --network=none --pull=false -t llm-gateway-admin-console:step13a ./admin-console
```

The image's offline dependency step failed with the exact npm message:

```text
npm error Exit handler never called!
process "/bin/sh -c npm ci --no-audit --no-fund" did not complete successfully: exit code: 1
```

No network workaround or host dependency installation was used. Therefore the
container image and complete containerized console-profile startup are **unverified**.
The successful alternative was local production Next.js and the real Python gateway
with Docker Postgres/Redis. The console CI job includes pinned install, lint,
typecheck, unit, build and real-stack e2e with service containers; remote CI has not
been run because the branch has not been pushed. Nothing was pushed or merged.

The final `git log --oneline main..HEAD` is included in the review handoff report.
