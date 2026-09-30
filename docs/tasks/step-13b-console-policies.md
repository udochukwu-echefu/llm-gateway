# Step 13b: Admin console, policy editors and cache purge

- **Branch:** `feat/step-13b-console-policies` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md` (especially Steps 9, 10, 11 and 13a),
  ADRs 0016-0022 and 0024, `docs/security/threat-model.md`, the README admin sections,
  `docs/tasks/step-13a-admin-console.md`, this spec
- **Needs:** Docker running (Postgres and Redis), Node 24.15.0. All npm dependencies are
  already installed; this step should need no new packages. If you truly need one, stop and
  report which one and why.

## Goal

Step 13a gave the console organisations, teams, keys, limits, budgets, usage and the audit
log. Every remaining admin API operation still needs `curl` or the CLI: **model policy,
guardrails, data residency and cache purge**. This step adds editors for them, which
completes the console. When 13b is merged, everything the admin API can do (except
managing admin keys, which stays CLI-only on purpose) can be done by clicking.

These settings are the most dangerous ones in the product. One click can block every model
for a whole organisation, or stop redacting card numbers. So this step is as much about
**safe editing** as about screens.

## How the policies work today (the API is the authority; do not reimplement it)

- **Model policy** (`/orgs/{org}/model-policy[?team=]`): a list of allowed patterns, each an
  exact catalogued model (`groq/openai/gpt-oss-20b`) or a provider wildcard (`groq/*`).
  Unknown patterns are rejected. The effective policy is the **intersection** of org and
  team. `null` (DELETE) means "no restriction at this level"; `[]` (PUT) means "allow
  nothing". Those are very different and the UI must never blur them.
- **Guardrails** (`/orgs/{org}/guardrails[?team=]`): `detector=action` pairs over 7 detectors
  and the actions `allow` < `redact` < `block`. Built-in defaults are a **floor**. The
  effective action is the **strictest** of default, org and team, so a weaker choice has no
  effect.
- **Residency** (`/orgs/{org}/residency[?team=]`): allowed regions out of `us`, `eu`, `cn`,
  `global`, `unknown`. Org and team **intersect**; `null` means unrestricted, `[]` blocks
  every model.
- **Cache purge** (`POST /orgs/{org}/cache/purge[?team=]`): removes that org's or team's
  cached responses, returns a count, is already audited (`cache-purge`), is best effort
  (new requests can refill during a purge), and returns 503 when Redis is unavailable.
- Each PUT **replaces** the whole list at that level. Org admins may edit their own org and
  teams; platform admins may edit any. Other orgs are 404, as in 13a.

## Decisions already made (binding; object in your report if you disagree)

### 1. Two small backend additions (Python, `admin/api`, tests, matrix rows)

- **`GET /admin/v1/catalog`:** the model catalogue for the editors: each model's
  `provider/model` name, provider, region, endpoints (chat/embeddings), and whether it is
  priced; plus aliases and their targets. Read-only, any authenticated admin, no secrets or
  provider URLs. Add it to the authorisation matrix.
- **Optimistic concurrency for policy writes.** Today, two admins editing the same policy
  means the second save silently erases the first ("lost update"). Fix it:
  - The GET responses for model-policy, guardrails and residency include a `version`: a
    stable hash of that level's stored override (org, or team when `?team=` is given).
  - PUT and DELETE on those endpoints accept `If-Match: "<version>"`. On a mismatch, return
    **412** with the standard error envelope and a stable code (e.g.
    `policy_version_conflict`) and change nothing. The check and the write happen in the
    same transaction, so two racing writers can't both pass.
  - `If-Match` stays optional in the API so the CLI keeps working, but **the console must
    always send it**.
  - Tests: a stale version gets 412 and no change; a fresh version succeeds; two concurrent
    writers with the same version produce exactly one success; the version changes after
    every successful write and clear.

### 2. Screens

- **Organisation page → "Policies" tab** (org level), and **team page → "Policies" tab**
  (team level), each with the three editors below. Each editor shows three things side by
  side: the **org** override, the **team** override (team tab only), and the **effective**
  result from the API, with a one-line plain explanation of how they combine ("Both lists
  must allow a model", "The strictest action wins").
- **Model policy editor:** choose "No restriction (inherit)", "Allow only these", or (as an
  explicit separate choice) "Allow nothing". "Allow only these" offers the catalogue grouped
  by provider, with a "whole provider" (`provider/*`) option. After saving, show the effective
  models and aliases **from the API response**, never computed in the browser.
- **Guardrails editor:** a semantic table of the 7 detectors: default, org, team (on the team
  tab), a choice of allow/redact/block for this level, and the effective action. When the
  chosen action is weaker than what is already enforced, say so inline ("No effect: the
  organisation already requires block"). Explain each detector in plain words.
- **Residency editor:** checkboxes for the five regions with short explanations (`global` =
  the provider may process anywhere; `unknown` = no verified region). "No restriction" and
  "Allow no regions" are separate explicit choices. After saving, show which models remain
  usable (from the API).
- **Cache purge:** on the org page (whole org) and the team page (that team). A danger-zone
  panel explaining what purge does and doesn't guarantee, then a confirmation dialog where
  the admin **types the org or team name** to enable the button. Show the purged count, and a
  plain message on 503.
- **Clearing** any override ("Remove override") uses a confirmation dialog naming the level.

### 3. Safe editing (the core of this step)

- **Dangerous-change confirmation:** saving "Allow nothing" for models or regions, or saving
  any change that **weakens** a guardrail override (e.g. org `card_number` from block to
  redact), requires a confirmation dialog stating the consequence in plain words.
- **Show the change before saving:** each editor shows a small "Changes" summary (added,
  removed, action changes) comparing the loaded value with the edited one. There's no save
  button while nothing has changed.
- **Conflicts:** the console sends `If-Match` with the version it loaded. On 412, keep the
  admin's edits on screen, show "Someone else changed this policy. Reload to see their
  version", and offer a reload. Never retry automatically.
- **Unsaved changes:** warn before leaving a tab or page with unsaved edits.
- All 13a rules still hold: every call goes through the BFF; the browser never sees the
  admin key; the BFF allowlist gets strict zod schemas for each new route (enum detectors,
  actions and regions; pattern regex; lists bounded and de-duplicated). `If-Match` is
  forwarded only on these routes and must match the version format. The Origin check and
  CSP are unchanged. The UI adapts to the role, but the API stays the only authority.

### 4. Code and design

- Same standards as 13a: small single-purpose modules, Prettier (100 columns), no
  catch-all helpers, labelled forms, semantic tables, keyboard-accessible dialogs, light and
  dark themes, and loading, empty and error states.
- Shared editor pieces (level switcher, change summary, confirmation, conflict banner) are
  components used by all three editors, not copied three times.

## Tests required

1. **Python:** `/catalog` (shape, no secrets, matrix row); every `If-Match` case above;
   matrix rows updated; existing policy tests still pass without `If-Match` (CLI path).
2. **Unit (Vitest):** the BFF schemas (reject unknown detector, region or action, bad
   patterns, oversized lists, bad `If-Match`); the change-summary logic; the "no effect"
   detection for guardrails.
3. **Component:** "Allow nothing" and guardrail weakening require confirmation; purge stays
   disabled until the exact name is typed; the conflict banner keeps the admin's edits.
4. **End-to-end (Playwright, real stack), each a named test:**
   - org admin sets an org model policy, the team narrows it, and the effective list shows
     the intersection; a model outside it is refused by the gateway's **public** API with the
     team's key;
   - tightening a guardrail changes the effective action; choosing a weaker one shows
     "No effect" and doesn't change the effective action;
   - residency `eu` only shrinks the usable models;
   - two browser contexts edit the same policy: the second save gets the conflict banner and
     the first admin's change survives;
   - cache purge requires the typed name and reports a count; with Redis stopped it shows the
     503 message (or document why that case is covered at a lower level instead);
   - an org admin can't view or edit another org's policies (URL tampering is "not found");
   - every write appears in the audit log;
   - the no-leak scan still covers every browser response in every test.
5. Before reporting, temporarily break each of these and confirm a test fails:
   - (a) the API ignores `If-Match`;
   - (b) the console stops sending `If-Match`;
   - (c) "Allow nothing" saves without confirmation;
   - (d) purge is enabled without typing the name;
   - (e) the BFF accepts an unknown detector.

## Docs and CI

- **ADR 0025:** safe policy editing (replace semantics, optimistic concurrency with
  `If-Match`/412, confirmations for dangerous changes, the effective view always comes from
  the API).
- **`docs/architecture.md`:** a "Step 13b" section in short plain-language paragraphs:
  - inheritance with a worked example (org allows `groq/*`, team allows one model → the team
    can use one model);
  - "strictest wins" for guardrails;
  - what a lost update is, and how optimistic concurrency prevents it (analogy: a shared
    document that warns "someone else edited this since you opened it");
  - why purge is best effort.
- **Threat model:** policy tampering, lost updates, accidental deny-all, purge abuse, UI-only
  checks.
- **README:** console section updated with new screenshots; remove "Model policy,
  guardrails, residency, cache purge … are 13b/later" (keep admin-key management and SSO as
  later).
- **Roadmap:** step 13 (admin console) complete.
- **CI:** the console job already runs format, lint, typecheck, unit and build; keep it green.

## Out of scope

Managing admin keys from the UI, SSO/OAuth, editing the catalogue or aliases,
multi-language UI, real-time push updates (the conflict check covers concurrent edits).

## Report back with

- Final output of the gateway gates (ruff, format, pyright, pytest, db, redis) and the
  console checks (format:check, lint, typecheck, unit, e2e with each test's name, build).
- The no-leak scan count, and the five break checks with the test that caught each.
- Screenshot paths, the design as built, open decisions, and dependencies added (expected:
  none).
- `git log --oneline main..HEAD`.
