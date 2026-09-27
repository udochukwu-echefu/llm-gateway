# Step 9: Model access policies, aliases and weighted routing

- **Branch:** `feat/step-9-routing-and-policies` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis)

## Goal

Today any team can use any catalogued model, and clients have to hard-code exact
provider model names. After this step:

1. **Access policies:** an organisation, and optionally each team, controls which
   models it may use. A team can only narrow its organisation's policy, never widen it.
2. **Aliases:** clients ask for `fast`, `smart` or `embed` instead of
   `groq/openai/gpt-oss-20b`. The platform team changes what an alias means in one
   reviewed place, and no client code changes.
3. **Weighted routing:** an alias can split traffic between models (e.g. 90/10), so a
   company can trial a new model on a slice of real traffic and compare cost and latency
   before switching.

## Decisions already made (binding; object in your report if you disagree)

### 1. Policies

- Stored in Postgres: an optional org policy and an optional team policy, each a list of
  model **patterns** (exact `provider/model`, or `provider/*`).
- **Effective policy = org ∩ team.** No org policy means every catalogued model is
  allowed at org level. No team policy means the team inherits the org policy. A team
  policy can **never** allow anything the org policy doesn't. Test this explicitly.
- Every pattern must match at least one catalogued model when it's set (catches typos
  like `grok/*`). Reject it otherwise, with a clear message.
- Loaded with the key lookup and cached in the verified-key cache, like limits. Changes
  take effect within the cache TTL, and the CLI says so.
- A denied model gets **403**, type `invalid_request_error`, code `model_not_allowed`,
  with a message naming the model and saying it isn't allowed for this team. Don't list
  which models *are* allowed (the team can call `/v1/models` for that).
- **Order of checks:** authenticate → resolve alias → policy → budget and limits → provider.
  Policy comes before limits, so a denied request doesn't consume RPM or budget.
- `/v1/models` returns only the models **and aliases** the caller's team may use.

### 2. Closing every bypass

The policy is checked on the **concrete model that will actually be called**, not just
on the name the client sent:

- **Aliases:** resolve the alias first, then check the concrete target. A team that isn't
  allowed DeepSeek can't reach it through an alias.
- **Weighted routing:** targets the team isn't allowed are removed before the weighted
  choice. If none are left → 403.
- **Fallback:** step 7 fallback targets are filtered by the same policy. A team that
  isn't allowed DeepSeek must **never** fall back to DeepSeek, even during a Groq outage.
  This is the most important test in this step.
- `provider_options` can't change the model (the canonical-field rule from ADR 0003
  already prevents it). Add a regression test anyway.

### 3. Aliases and weighted routing (in the reviewed catalogue)

```toml
[aliases.fast]
targets = [
  { model = "groq/openai/gpt-oss-20b", weight = 90 },
  { model = "deepseek/deepseek-flash", weight = 10 },
]

[aliases.embed]
targets = [{ model = "gemini/gemini-embedding-2", weight = 100 }]
```

- An alias name has **no slash** (`^[a-z][a-z0-9-]{0,31}$`), and every real model has
  one, so the two can never be confused. An alias can't equal a provider name.
- Validation at startup: every target is in the catalogue; all targets have the same
  `kind`; weights are positive integers; no alias refers to another alias.
- Weighted choice uses an injectable random source. Record the **alias** on each usage
  record (new nullable column, `alias`) and add it as a bounded metric label on
  `lgw_upstream_requests_total`, so a 90/10 trial can be compared with SQL and in Grafana.
- The response's `model` stays the concrete model that served the request (transparency
  from step 7). Add an `x-lgw-alias: fast` response header when an alias was used.
- Unknown names without a slash → 404 `model_not_found`, listing the aliases the
  caller's team may use.

### 4. CLI (every change audited, same transaction, as in step 8)

```bash
uv run gateway-admin set-models <org> [--team T] --allow "groq/*" --allow "deepseek/deepseek-flash"
uv run gateway-admin clear-models <org> [--team T]
uv run gateway-admin show-models <org> [--team T]   # org policy, team policy, effective models and aliases
```

`show-models` prints a readable table in the style of step 6's `show-limits`.

## Tests required

1. Effective policy for each combination (none/org/team/both), including a team pattern
   that tries to widen the org policy.
2. Pattern validation (unknown provider, typo, exact model, wildcard).
3. Denied model → 403 with **no** provider call and **no** RPM/budget consumed.
4. Alias resolution, the 404 for unknown aliases, and every alias validation rule.
5. Weighted routing: a fixed random sequence gives the expected targets; disallowed
   targets are filtered out; all filtered → 403; the alias is recorded on usage records
   and in metrics.
6. **Fallback bypass:** the requested model's breaker is open, its catalogue fallback is
   DeepSeek, and the team isn't allowed DeepSeek → no DeepSeek call is made (assert the
   mock), and the client gets 503 `provider_unavailable`.
7. `/v1/models` per team, including aliases.
8. CLI set/clear/show with audit events (`db`).
9. Cache: a policy change takes effect after the TTL.
10. Live: an alias resolves to a real provider end to end (`live`).
11. Before reporting, temporarily break each of these and confirm a test fails: (a) check
    the policy on the alias name instead of the resolved model, (b) skip policy filtering
    of fallback targets, (c) use team policy alone instead of org ∩ team, (d) check the
    policy after limits.

## Docs required

- **ADR 0016:** access policies (intersection semantics, allow-by-default at org level,
  where the check sits and why it runs on the resolved model).
- **ADR 0017:** aliases and weighted routing (catalogue-reviewed, no-slash naming,
  per-record alias for trial analysis).
- **`docs/architecture.md`:** a "Step 9" section in plain language: why policies must
  check the *final* destination (analogy: checking a passenger's ticket at the gate,
  not just at the booking desk), what an alias buys a platform team, and how a 90/10 trial
  works.
- **Threat model:** alias, fallback and weighted-route bypass, and the policy cache delay.
- **README:** aliases, the policy CLI, error codes and headers. **Roadmap:** step 9 done,
  step 10 next.

## Out of scope

Per-key model scopes, cost- or latency-aware automatic routing, sticky routing per user,
prompt-based routing, per-model rate limits.

## Report back with

- Final output of the four gates and the db, redis and live tests (exact AGENTS.md
  commands).
- The effective-policy truth table your tests cover.
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
