# Step 13a review corrections and validation

Date: 2026-09-30. Repository: `/Users/udo/claude sessions/llm-gateway`.
Branch: `feat/step-13a-admin-console`. No push or merge.

## Corrections delivered

All ten review findings are addressed. Valid admin credentials authenticate even after
invalid attempts exhaust the shared-IP failure quota; invalid attempts still receive
429. Constant-time verification and error envelopes remain intact. ADR 0022 explains
the cheap key lookup/HMAC trade-off. The console also throttles failed login attempts
per client address, in memory per process/replica.

Unpriced costs and savings are JSON null through the HTTP API. The console has no
string-None compatibility checks and explicitly displays unpriced usage. The shared
zod configuration schema now runs before Next starts in development, local production
and the Docker entrypoint. Compose rejects a missing session secret during interpolation.

The console decision is ADR 0024; ADR 0023 remains controlled load testing. The eight
requested modules were refactored in a standalone behavior-preserving commit. Browser
coverage now comprises seven named tests with shared fixtures. The usage view has
requests and tokens charts, labelled axes, a legend and a semantic daily-values table;
unknown token totals leave gaps. Sidebar backgrounds extend to the whole page in both
themes. The architecture section uses short explanatory paragraphs. The three stale
status/durability/cache-restoration statements were corrected in a separate docs commit.

## Gateway gates

Postgres and Redis were running through Docker Compose. The database and Redis suites
ran sequentially, followed by e2e. Installed `.venv` executables avoid cache restrictions.

| Gate / command | Final output |
| --- | --- |
| `.venv/bin/ruff check --no-cache .` | `All checks passed!` |
| `.venv/bin/ruff format --no-cache --check .` | `345 files already formatted` |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/pytest -p no:cacheprovider -q` | `1012 passed, 160 skipped, 25 deselected in 18.78s` |
| Same pytest invocation with `-m db`, database environment set | `95 passed, 11 skipped, 1091 deselected in 28.11s` |
| Same pytest invocation with `-m redis`, database and Redis environment set | `65 passed, 1132 deselected in 48.77s` |

The browser stack and seed harness also passed an explicit pyright check. Ruff,
format and pyright were repeated successfully after the break checks restored sources.

## Console checks

Checks used Node 24.15.0, prepared pinned dependencies and installed Chromium.

| Command | Result |
| --- | --- |
| `npm run lint` | Exit 0; no ESLint diagnostics |
| `npm run typecheck` | Exit 0; no TypeScript diagnostics |
| `npm test` | `Test Files 9 passed (9)`; `Tests 32 passed (32)` |
| `npm run build` | Exit 0; Next.js 16.3.7 production build succeeded |
| `npm run test:e2e` | `7 passed (13.9s)` against the disposable real stack |
| `npm run test:break` | All six intended regressions caught; source restored and clean build regenerated |

| E2E test name | Result | Browser responses scanned |
| --- | --- | ---: |
| `platform workflow` | Passed | 82 |
| `one-time key dialog` | Passed | 52 |
| `org-admin isolation and URL tampering` | Passed | 72 |
| `security headers and CSP` | Passed | 49 |
| `cookie flags and cross-origin POST` | Passed | 23 |
| `revocation logs out` | Passed | 48 |
| `login throttle and no shared-IP lockout` | Passed | 69 |

**No-leak result: 395 browser responses; zero leaks; exactly one permitted
key-creation response.** An automatic fixture attaches the scanner before each test,
checks every received body and header against captured complete bytes, and aggregates
coverage. It also checks captures cancelled during navigation. Only the creation
response's key field is permitted, owned by the one-time-dialog test. No traces,
videos or secret-dialog screenshots were retained. The disposable database count was
zero and the ignored credential state file was absent after cleanup.

The login e2e test sends more than 20 bad login requests from a real IPv4 client while
an existing admin and a new login use a real IPv6 browser client. Rotating forged
forwarding/internal headers do not avoid the abusive client's 429. Separately,
exhausting the gateway's shared BFF-IP quota does not block the signed-in admin or a
valid new sign-in. No model provider is called.

## Six deliberate break checks

Each check temporarily changed production source, required the designated assertion
or test to fail, and restored the original bytes in a finally block.

| Break | Test that caught it |
| --- | --- |
| (a) Pass the admin credential into client Shell props | The automatic Playwright no-leak fixture across the seven e2e tests; `Admin credential in response` assertion |
| (b) Drop the Origin check | `mutating HTTP handlers reject cross-origin and missing Origin before any mutation` |
| (c) Retain the created secret and add a Reveal key again control | `the created key cannot be reopened after closing` |
| (d) Remove cookie httpOnly | `round trip encrypts the credential and has secure cookie flags` |
| (e) Check the failure limit before validating the admin key | `test_valid_admin_bypasses_exhausted_failure_limit` |
| (f) Serialize absent cost/savings as the string None | `test_unpriced_usage_is_json_null` |

All six were caught. The normal unit and e2e suites passed after restoration. No
intentional vulnerability remains in the branch.

## Client address and trust

The installed Next 16.3.7 source shows that route handlers receive a Web Request with
headers, without the Node socket address. Its base server preserves incoming
X-Forwarded-For. Consequently, reading that header by itself is unsafe.

The console entrypoints install a Node 24 `diagnostics_channel` subscriber on
`http.server.request.start`. Node publishes the request and socket before dispatching
the request listener. The subscriber overwrites `x-console-client-address` with a
validated address from `socket.remoteAddress`. A caller's value for this internal
header cannot survive. IPv6 and IPv4-mapped IPv6 addresses are normalized.

`ADMIN_CONSOLE_TRUSTED_PROXY_HOPS` is validated as an integer 0–32 and defaults to 0:
forwarded headers are ignored. When explicitly configured to N, the Nth address from
the right of X-Forwarded-For is selected and validated; a missing/invalid selection
falls back to the socket. Behind a load balancer, restrict direct console access to
trusted proxies, ensure they append actual peers or replace untrusted chains, and set
the exact hop count. With the default, all users behind that balancer share its socket
quota. NAT users also share a quota. The ten-failure/60-second throttle is per replica,
resets on restart, and has bounded memory; it is not a distributed abuse-control service.

Development worker header handling also passed a live smoke test: rotating forged IP
headers could not prevent the eleventh malformed login from returning 429.

## Refreshed screenshots

All nine images were re-taken after the chart and sidebar fixes using synthetic data
and public identifiers only. Full-page tablet and light/dark usage images were visually
inspected. Paths relative to the repository:

- `docs/images/console-login.png`
- `docs/images/console-organisations.png`
- `docs/images/console-usage.png`
- `docs/images/console-keys.png`
- `docs/images/console-limits.png`
- `docs/images/console-budget.png`
- `docs/images/console-audit.png`
- `docs/images/console-usage-dark.png`
- `docs/images/console-tablet.png`

## Design, decisions and dependencies

The calm operations console retains light/dark themes, system fonts, keyboard focus,
native dialogs, labelled forms and semantic tables. Server route handlers form the
BFF; encrypted Secure/httpOnly/Strict cookies enforce eight-hour absolute and
30-minute idle sessions. Every mutation checks the configured Origin, pages use
nonce CSP, and the gateway remains the authorization authority. Tenant secrets are
shown once. Money arithmetic uses exact decimal strings and BigInt. UTC defines
monthly usage windows. Native SVG charts now separate request and token scales.

No implementation decision remains open. Step 13b editors remain out of scope.
No new package was added or version changed during these corrections. Previously
approved additions beyond the original spec remain: TypeScript and Node/React types,
ESLint and eslint-config-next, @tailwindcss/postcss and postcss, jsdom,
@vitejs/plugin-react, @testing-library/dom and @testing-library/user-event. TypeScript
stays 5.9.3, ESLint 9.39.5 and Node 24.15.0. Vite 8's built-in tsconfigPaths is used.
Docker now explicitly copies the existing pinned zod dependency into the standalone
runtime because Next's trace otherwise does not include the startup validator.

## Verification limits and alternatives

The ordinary image build was attempted without an offline/cache/proxy workaround:

```text
docker build --pull=false -t llm-gateway-admin-console:step13a-review ./admin-console
```

It failed at `RUN npm ci --no-audit --no-fund`, exit 1, with:

```text
npm error code ECONNRESET
npm error network aborted
ERROR: failed to build: failed to solve: process "/bin/sh -c npm ci --no-audit --no-fund" did not complete successfully: exit code: 1
```

Registry connectivity therefore blocked verification of the new Docker image and
complete containerized console startup. No network workaround or dependency change
was used. Instead, the exact Docker startup script was smoke-tested against a native
standalone directory assembled with the Dockerfile's copied files and installed pinned
zod: invalid settings exited 1 before Ready, and valid fake settings served `/login`
with 200. Startup unit tests exercised missing/short secrets and invalid URLs through
both startup scripts. Local production e2e with Docker Postgres/Redis passed. Compose
configuration validation passed, and omitting the secret caused the expected
interpolation failure.

An initial additional IPv4 loopback source bind to 127.0.0.2 failed with
`EADDRNOTAVAIL` on this machine. The final test instead uses actual IPv4 and IPv6
loopback clients; no system alias was configured.

Remote CI has not run because the branch was not pushed. The existing console job
covers lint, types, unit, build and real-stack e2e with service containers. Nothing was
pushed or merged. The final `git log --oneline main..HEAD` is included in the handoff.
