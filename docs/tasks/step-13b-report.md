# Step 13b validation report

Implemented on `feat/step-13b-console-policies`, based on main at `28168a1`.
The spec was the first commit; the compose regression fix followed before feature work.
The branch is for reviewer inspection: nothing was pushed or merged.

## Built and design as delivered

- Authenticated catalogue read; transactionally checked If-Match/412 policy replacement,
  revision migration 0010, CLI compatibility and authorization matrix coverage.
- Shared org/team model, guardrail and residency editors, API-effective views, change
  summaries, explicit inherit/deny-all, consequence confirmations, preserved conflict
  drafts, explicit reload, unsaved navigation warnings and strictly validated BFF writes.
- Org/team Cache panels with exact-name confirmation, purged counts and Redis 503 messages.
- Overview after sign-in: scoped org inventory, six cards, requests chart with accessible
  table alternative, top five models, budget alert badges and five recent audit events.
- Helpful empty states for organizations, teams, keys, usage and filtered audit results;
  the copyable curl contains only YOUR_TEAM_API_KEY.
- Opt-in Demo Co seeder: Search, Support and Engineering, six key records, budgets/limits
  and 855 synthetic receipts over 30 days, including unpriced/cache-hit rows. No providers.
- Fixed-point Decimal money in admin usage/budget responses, CLI usage and new budget
  audit details, with real PostgreSQL zero-cost and zero-savings regression assertions.
- ADR 0025, plain-language architecture Step 13b, threat model, README/screenshots and
  roadmap marking step 13 complete.

The console keeps the existing restrained green accent, semantic tables, labelled controls,
keyboard dialogs, system/light/dark themes and responsive desktop/tablet layout. Policy
panels compare saved org/team overrides beside API results; dangerous actions name their
scope and consequence. Overview shows priced amounts and explicitly flags unpriced calls
and partial tokens. Wide tables scroll within their panels instead of overflowing the page.
No changed Python/TypeScript/TSX/JavaScript source module exceeds 400 lines.

## Decisions and limitations

I disagree with interpreting the spec's version as a **value-only** hash: it cannot also
change after every repeated save/clear, and changing then restoring a value revives an old
hash. The chosen hash includes owner ID, policy kind, stored override and a monotonic
revision. It is stable between writes and changes after every successful write, including
unconditional CLI writes. This is the only literal departure from that interpretation of
the binding decisions; ADR 0025 explains it. No functional requirement was omitted.

Other open implementation choices:

- Separate Policies and Cache tabs; shared list editor for models/regions, shared frame,
  confirmation, change tracking and conflict handling across all editors.
- Guardrail Inherit removes a detector override; lower choices show the applicable floor.
- A successful write followed by a failed refresh is reported accurately and blocks further
  writes until reload. It is never silently retried or mislabelled as another admin's edit.
- Native dialogs and browser navigation guards cover tabs, links, sign-out, Back/Forward
  where cancellable, and beforeunload exits. Browser support for native traversal warnings
  varies; Chromium Back cancellation was verified end-to-end.
- Overview uses **existing endpoints only**, exhausting pagination. Top models rank by
  priced spend; budget proximity compares exact spend/budget ratios. Requests retain the
  usage API's provider-attempt/cache-hit semantics. Latest audit IDs are selected after
  reading the ascending audit pages. Large histories may warrant a separately reviewed
  reverse-page API later; multiple endpoint reads are not one atomic snapshot.
- Money uses format(value, "f") without floating-point conversion or rounding; a zero
  PostgreSQL Numeric(20, 12) sum is "0.000000000000", never "0E-12". Unknown values
  stay null/NULL. Existing hashed audit records are not rewritten.
- Current reviewed catalogue entries have no verified EU processing region. EU-only
  correctly produces zero usable models; no regional guarantee was invented.
- Demo secrets are discarded, not printed. Deterministic receipt IDs and a seed lock make
  reruns idempotent; existing edits/receipts are preserved. Synthetic past usage uses
  today's reviewed prices for illustration, not historical invoices. Later runs append
  new dates. An existing non-demo Demo Co is refused. The Search budget demonstrates an
  above-threshold badge.
- Redis outage is covered by HTTP `test_redis_outage_returns_503_without_audit_or_scope_leak`
  (a Redis connection exception, authorization before purge, no success audit), plus the
  component `503 purge explains Redis availability without claiming success`. Shared local
  Redis was not stopped; the spec explicitly permits documenting lower-level coverage.

Dependencies added: **none**. No npm install, sudo, force, live-provider calls or secret
output. Node was 24.15.0; Next was 16.3.7, with version-specific behavior checked in its
installed documentation. No learning-guide branch/worktree was touched.

## Final gateway and console gates

The installed .venv executables and no-cacheprovider fallback permitted by AGENTS.md were
used for gateway gates. Test Postgres used the fake local fixture URL; Redis used DB 15.
The database suite finished before Redis, then console e2e. No tight timing assertions.
All commands below exited 0. Reported skips/deselections are retained, not counted as passes.

### Gateway ruff (.venv/bin/ruff check .)

```text
All checks passed!
```

### Gateway format (.venv/bin/ruff format --check .)

```text
358 files already formatted
```

### Gateway pyright (.venv/bin/pyright --pythonpath .venv/bin/python)

```text
0 errors, 0 warnings, 0 informations
```

### Gateway pytest (.venv/bin/pytest -q -p no:cacheprovider)

```text
1013 passed, 192 skipped, 25 deselected in 20.38s
```

### Database suite (-m db)

```text
127 passed, 11 skipped, 1092 deselected in 36.44s
```

### Redis suite (-m redis)

```text
65 passed, 1165 deselected in 48.49s
```

### Console format:check

```text
Checking formatting...
All matched files use Prettier code style!
```

### Console lint

```text
> eslint .
Exit 0; no diagnostics.
```

### Console typecheck

```text
> tsc --noEmit
Exit 0; no diagnostics.
```

### Console unit/component

```text
Test Files  13 passed (13)
Tests  54 passed (54)
Duration  1.89s (environment 64%, tests 14%, setup 10%, transform 9%, import 3%)
```

### Console production build

`npm run build` exited 0 with obviously fake build configuration.

```text
▲ Next.js 16.3.7 (Turbopack)
✓ Compiled successfully in 525ms
✓ Generating static pages using 11 workers (9/9) in 113ms
ƒ Proxy (Middleware)
ƒ (Dynamic) server-rendered on demand
```

Routes include `/overview`, org/team pages, audit, login and the server BFF.
Formatting, lint and typing were checked again after restoring the break mutations.

### Console e2e: each named test

`CONSOLE_TEST_PORT=3110 CONSOLE_SCREENSHOTS=1 npm run test:e2e` exited 0.
Port 3100 was already occupied by an existing local Node process, causing the first
server-start attempt to fail; the configurable 3110 test port resolved it without stopping
that process. Initial richer-fixture failures exposed two old small-fixture assumptions
(audit-page count and unique “Unpriced usage” text); the assertions now handle pagination
and multiple teams. The final production run below passed.

```text
✓   1 tests/e2e/console.spec.ts:4:5 › platform workflow (5.2s)
✓   2 tests/e2e/console.spec.ts:85:5 › one-time key dialog (2.0s)
✓   3 tests/e2e/console.spec.ts:111:5 › org-admin isolation and URL tampering (1.8s)
✓   4 tests/e2e/console.spec.ts:131:5 › security headers and CSP (1.9s)
✓   5 tests/e2e/console.spec.ts:171:5 › cookie flags and cross-origin POST (1.1s)
✓   6 tests/e2e/console.spec.ts:189:5 › revocation logs out (1.5s)
✓   7 tests/e2e/console.spec.ts:202:5 › login throttle and no shared-IP lockout (2.5s)
✓   8 tests/e2e/empty-states.spec.ts:2:5 › empty workspace guides first team key request and unmatched audit filter (2.4s)
✓   9 tests/e2e/overview.spec.ts:5:5 › Overview landing numbers match the seeded org usage API and org scope (1.0s)
✓  10 tests/e2e/overview.spec.ts:69:5 › Overview platform landing includes all organisations and recent activity (1.3s)
✓  11 tests/e2e/policies.spec.ts:23:5 › org policy and team intersection enforced by public API (2.3s)
✓  12 tests/e2e/policies.spec.ts:64:5 › guardrail tightening and weaker choice has no effect (2.1s)
✓  13 tests/e2e/policies.spec.ts:95:5 › EU residency shrinks usable models using the API view (1.8s)
✓  14 tests/e2e/policies.spec.ts:119:5 › two browser contexts preserve the first policy and keep the conflicted draft (3.0s)
✓  15 tests/e2e/policies.spec.ts:153:5 › cache purge requires a typed name and reports its count (2.0s)
✓  16 tests/e2e/policies.spec.ts:166:5 › org admin cannot view or edit another org policies by URL tampering (1.7s)
✓  17 tests/e2e/policies.spec.ts:194:5 › every policy write and cache purge appears in the audit log (3.3s)
✓  18 tests/e2e/policies.spec.ts:244:5 › unsaved policy changes warn before tab page and browser Back navigation (1.6s)
18 passed (44.7s)
```

## No-leak scan and five break checks

```text
No-leak scan total: 1277 browser responses; 1 permitted key-creation response; zero leaks.
```

Every browser response body and header in every test is scanned, including both contexts
of the conflict test and the new Overview tests. Exactly one tenant key-creation response
is permitted to contain its one-time secret; no admin credential is permitted anywhere.
No traces, videos, key-dialog screenshots or .env files were committed.

`npm run test:break:policies` exited 0. Each mutation failed its designated behavior
assertion (not a compile error), then the runner restored every source:

```text
a API ignoring If-Match: test_fresh_stale_clear_and_repeated_writes PASS
b console omitting If-Match: model-policy deny-all requires confirmation before a conditional write PASS
c deny-all without confirmation: model-policy deny-all requires confirmation before a conditional write PASS
d purge enabled without typing: purge requires the exact typed name before calling the BFF PASS
e BFF accepting unknown detector: strict policy schemas reject unknown detectors actions regions and bad patterns PASS
All five policy mutations caught; every source restored.
```

Check (a)'s exact Python case was
`test_fresh_stale_clear_and_repeated_writes[org-model-policy-body0]`.

## Compose and seeder verification

- `env -u ADMIN_CONSOLE_SESSION_SECRET docker compose up -d postgres redis`: exit 0,
  database/cache services running without the console variable.
- `env -u ADMIN_CONSOLE_SESSION_SECRET docker compose --profile console up -d`: images
  built successfully; console container exited 1 with the clear startup error below.
  Only the verification gateway/console containers were stopped afterwards.

```text
Invalid console configuration: check ADMIN_API_URL, ADMIN_CONSOLE_ORIGIN, a session secret of at least 32 bytes and trusted proxy hops (0–32).
```

- `uv run python scripts/seed_demo.py`, with GATEWAY_DEMO_SEED=1 and fake configuration,
  ran twice in a disposable migrated database: 1 org, 3 teams, 6 keys, 855 rows on both
  runs; identical IDs/name-only output, no duplicates. Without opt-in it refuses with exit 1.
- No unresolved sandbox execution failure. Docker image builds did not fail for network.
  GitHub-hosted CI was not run because this branch was intentionally not pushed; the
  requested local gateway and console checks all passed. Remote CI results are not claimed.

## README screenshot paths

Captured from the disposable stack using the real demo seeder; only synthetic metadata
and public IDs appear. Light/dark desktop and 820px tablet screenshots were inspected.
New step 13b/Overview images:

- `/Users/udo/claude sessions/llm-gateway/docs/images/console-overview.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-overview-org.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-overview-dark.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-overview-tablet.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-policies-org.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-policies-team.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-policies-dark.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-policies-tablet.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-cache-purge.png`

Existing README captures retained/refreshed:

- `/Users/udo/claude sessions/llm-gateway/docs/images/console-login.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-organisations.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-usage.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-keys.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-limits.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-budget.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-audit.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-usage-dark.png`
- `/Users/udo/claude sessions/llm-gateway/docs/images/console-tablet.png`
