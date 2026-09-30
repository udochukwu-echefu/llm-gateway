# ADR 0024: Admin console with a server-side credential boundary

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

The private API already enforces platform and organization roles. Administrators need
an accessible browser interface without distributing their administrative credential
through React props, HTML, JavaScript or JSON responses. The console decision is 0024; decision 0023 covers controlled load testing.

## Decision

Use Next.js 16.3.7 App Router, React 19.3, strict TypeScript and Tailwind 4 in
admin-console/. Follow the installed Next.js documentation rather than older conventions.
The browser calls same-origin route handlers, the **backend for frontend (BFF)**.
Only server-only modules call ADMIN_API_URL. Route handlers permit the 13a operations
explicitly, validate mutation bodies (names cannot contain a slash or be dot traversal), preserve the supplied org scope and credential,
and never manufacture privileges. The gateway API is the authorization authority.
GET /admin/v1/me supplies public identity and an optional organization {id, name}.

The pasted admin credential is validated with /me and sealed using iron-session 9
in a __Host-lgw-console cookie: Secure, httpOnly, SameSite=Strict and Path=/.
The runtime secret must have at least 32 characters and 32 bytes. Sessions enforce
8 hours since sign-in and 30 minutes since the last authenticated request. Activity
refreshes the idle timestamp, never the original sign-in time. Login replaces the
previous session; logout clears it. Gateway 401 destroys the cookie and causes a
full navigation to login. Credentials and exception details are never logged.
Deployment URLs and session secret are validated with zod at server startup.

Every mutation, including login/logout, checks Origin against ADMIN_CONSOLE_ORIGIN.
No request Host or forwarded header expands that trust. There are no Server Actions;
Next's built-in Server Action Origin/Host comparison is therefore not our defence.
If actions are added, retain equivalent explicit configured-origin checks. Missing
Origin is rejected. Only the authenticated gateway decides role and organization access.

proxy.ts supplies fresh script/style nonces on request and response CSP headers.
The root layout uses connection() for dynamic rendering. CSP has strict-dynamic,
frame-ancestors 'none', object-src 'none', base-uri 'none' and form-action 'self';
production scripts have neither unsafe-inline nor unsafe-eval. Development alone
allows unsafe-eval as required by the installed docs. Fonts are local system fonts;
CSS is external and charts use SVG, avoiding inline style exceptions. Referrer-Policy
is no-referrer and X-Content-Type-Options is nosniff. Authenticated data and BFF replies
are no-store. No third-party network resources, analytics or browser-held admin keys.

Creation forms generate one UUID per submitted body. Double-clicks are locked out;
a retry keeps the UUID until success or editing the body. Key creation releases only
the first response's tenant secret to a native dialog. Closing/Escape, navigating away,
changing tabs or reloading discards the state; no reveal control or browser storage
retains it. A replay without the secret asks the operator to revoke and replace it.
Upstream headers are never forwarded; credential-shaped text is redacted even in errors.

Money remains decimal strings. BigInt pico-dollar arithmetic supports exact formatting,
comparison and integer progress percentages, including Python Decimal exponent notation.
Unknown cost and partial unpriced usage are explicitly labelled. Month boundaries are UTC,
matching the gateway. Usage pagination is exhausted before ranking or totals are displayed.
URL segments are decoded once and re-encoded before calling the API, preserving spaces,
Unicode, literal percent signs, question marks and fragment characters without changing scope.
Native dialog implements focus containment/Escape; semantic tables, labelled fields,
visible focus and system/light/dark themes cover desktop and tablet. Theme choice lasts
for the current document; default follows the operating system. No persisted theme or
inline bootstrap script is needed. A small SVG request trend and exact token table keep
charts readable without loading Recharts into the browser bundle.

## Dependencies

The spec allows next, react, react-dom, tailwindcss, iron-session, zod, recharts,
vitest, @testing-library/react and @playwright/test. Recharts is pinned in the prepared
manifest but unused; SVG avoids an additional chart abstraction and inline style CSP conflicts.
Approved additions are typescript, @types/node, @types/react, @types/react-dom,
eslint, eslint-config-next, @tailwindcss/postcss, postcss, jsdom, @vitejs/plugin-react,
@testing-library/dom and @testing-library/user-event. They provide strict typing,
Next lint rules, Tailwind 4's PostCSS integration and DOM/component interaction tests.
TypeScript stays 5.9.3 (typescript-eslint supports <6.1) and ESLint stays 9.x
(Next lint plugins do not support ESLint 10). Node is pinned to 24.15.0.
Vitest uses Vite 8 resolve.tsconfigPaths; no vite-tsconfig-paths package is added.
server-only is Next's existing compiler marker, not an added npm dependency.

## Consequences

HTTPS is required in deployment; local Chromium treats localhost as trustworthy for
Secure cookies. The compose console binds to loopback and keeps the admin port private
inside its network. The gateway requires its existing pepper/provider configuration;
no provider is contacted by the browser test harness (its only provider URL is port 1).

An encrypted cookie is still a bearer credential: stolen ciphertext can be replayed.
Stateless logout clears this browser but cannot revoke a previously stolen cookie;
revoke the underlying admin key to invalidate it. XSS can perform same-origin actions
while a session exists, though it cannot read the admin credential. CSP is defence in
depth. Audit verification retains ADR 0015's database-owner limitations. Current usage
is best effort, and unknown costs are not an invoice. Admin-key management, SSO and
step 13b policy editors remain out of scope.

## Alternatives considered

- Browser-held admin credential: makes XSS and bundle/data leaks administrator compromise.
- UI-only role checks: cannot prevent a crafted request to another organization.
- Server Actions for every operation: valid, but explicit route-handler boundaries are
  easier to exercise through HTTP, audit and pair with the existing REST API here.
- Floating-point money: fails exact decimal accounting.
- External fonts or elaborate charts: require unnecessary network/CSP exceptions.

## Amendment: startup and browser-client throttling (2026-09-30)

Both production entry points validate the same zod schema before loading Next or
opening a listener. The Docker CMD runs the checked entry point. Compose refuses
a missing session secret during configuration interpolation. Instrumentation keeps
a defence-in-depth check, but is not the startup guarantee.

Next 16.3.7's `NextRequestAdapter.fromNodeNextRequest` copies headers into the Web
Request and does not expose the socket. `base-server.js` sets X-Forwarded-For only
when absent, so a Route Handler cannot safely treat that header as the client IP.
Node 24's `http.server.request.start` diagnostics channel runs before the request
listener. The entry points subscribe there and overwrite `x-console-client-address`
with the socket address. Route Handlers trust only this overwritten header. The
standard generated standalone Next server is retained; no custom Next server or
new dependency is required. Development propagates the preload to its worker.

`ADMIN_CONSOLE_TRUSTED_PROXY_HOPS` is an integer 0–32, default 0. Zero ignores every
forwarded address. With N trusted hops, select the Nth address from the right of
X-Forwarded-For and validate it; missing/invalid selected values fall back to the socket. Deployments
behind a load balancer must restrict direct access to the console, ensure the trusted
proxy appends the actual peer (or replaces an untrusted chain), and set the exact hop
count, mirroring the gateway. Setting hops on a publicly reachable origin would let
attackers claim addresses. With hops zero behind a balancer, its socket IP shares
a login quota; operators must configure that topology deliberately.

Ten failed sign-ins per client within a fixed minute trigger 429 with a plain message
and Retry-After. Malformed keys and upstream authentication rejections count; Origin
rejections and gateway outages do not. Successful sign-in clears that client's count.
The throttle is bounded to 10,000 entries, in-memory and per replica; restart resets
it and replicas do not share counters. Oldest entries can be evicted under pressure,
so it is best effort rather than a distributed rate-limit guarantee. Load balancers
should add their own abuse controls for larger deployments. Already authenticated
requests are never subject to this login throttle. Gateway valid keys bypass its
shared-IP authentication-failure limiter, as amended in ADR 0022.
