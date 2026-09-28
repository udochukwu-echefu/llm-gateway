# Step 11: Guardrails: PII and secret redaction, and data residency

- **Branch:** `feat/step-11-guardrails` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, this spec
- **Needs:** Docker running (Postgres and Redis)

## Goal

The gateway is the last place a company can inspect data before it goes to a third
party. After this step:

1. **Secrets** (API keys, private keys) pasted into prompts are **blocked** before they
   leave, by default.
2. **Personal data** (emails, phone numbers, card numbers, IBANs, IP addresses) can be
   **redacted**: the provider sees `[EMAIL_1]`, and the client still gets a useful
   answer, with the original values put back where the model repeated the placeholders.
3. **Data residency:** an organisation can say "our data may only be processed in these
   regions", and models hosted elsewhere become unreachable for it, including through
   aliases and fallback.

## Decisions already made (binding; object in your report if you disagree)

### 1. Detectors (deterministic, no ML, no new dependency)

| Detector | Examples | Validation to cut false positives |
|---|---|---|
| `secret_api_key` | `sk-…`, `gsk_…`, `AIza…`, `ghp_…`, `AKIA…`, **our own `lgw_…` keys** | prefix + length/charset |
| `secret_private_key` | `-----BEGIN … PRIVATE KEY-----` blocks | full block match |
| `email` | `ada@example.com` | RFC-ish pattern, TLD required |
| `phone` | `+2348012345678`, `0801 234 5678`, `+1 (415) 555-0100` | digit count 7–15 after normalising |
| `card_number` | 13–19 digits, with spaces or dashes | **Luhn checksum** |
| `iban` | `GB82 WEST 1234 5698 7654 32` | **mod-97 checksum** |
| `ip_address` | IPv4 and IPv6 | each octet ≤ 255 |

- Compiled regexes with **no catastrophic backtracking**. Test against adversarial
  inputs (e.g. 100 KB of `a@a.a@a…`, long digit runs) with a time bound. Explain ReDoS
  in the ADR.
- Scan **all** text the provider will see: every message's text content (system,
  developer, user, assistant history, tool results), tool-call arguments, and embedding
  inputs. Images and files are not scanned. Document that honestly.
- The scanner is a pure function (text → findings with span and type), fully
  table-tested with true **and** false positives for each detector.

### 2. Actions and policies

- Each detector has an action: `allow`, `redact` or `block`.
- **Defaults:** secret detectors `block`, `card_number` and `iban` `redact`, everything
  else `allow`. Explain the choice (secrets have no legitimate reason to reach a model;
  PII sometimes does).
- Org and team guardrail policies are stored in Postgres, changed only through the CLI
  (audited, same transaction), and cached with the key (as in steps 6 and 9).
- **Effective action = the strictest of org, team and default** (`allow < redact <
  block`). A team can tighten but never loosen. That mirrors step 9's "narrow only", so
  test it the same way.
- `block` → **400**, type `invalid_request_error`, code `guardrail_blocked`. The message
  lists the **detector types** found, and **never** the matched values.

### 3. Redaction and restore

- Redaction replaces each match with a typed placeholder, **consistent within one
  request**: the same email twice → `[EMAIL_1]` both times, a second email → `[EMAIL_2]`.
  So the model can still reason ("reply to [EMAIL_1]").
- **Restore (non-streaming):** the mapping lives **only in memory for that request**.
  After the response comes back, placeholders the model repeated are replaced with the
  original values before the response reaches the client. The provider never sees the
  real values, and the client still gets a natural answer. The mapping is never logged,
  traced, cached or persisted.
- **Streaming:** input redaction applies as usual. Output **restore** needs a small
  hold-back buffer, because a placeholder can be split across chunks (`[EMA` + `IL_1]`).
  Implement it: hold back text only while an unfinished `[…` could still become a
  placeholder, bounded by the longest possible placeholder. Test the split cases,
  including a placeholder split across three chunks.
- **Output scanning** (did the model produce new PII or secrets?): for non-streaming
  responses, apply the effective action (`redact` → placeholder-style masking; `block` →
  502 `guardrail_blocked_output`). For **streams, detect only**, recording findings in
  metrics and logs once the stream ends. Explain why: bytes already sent can't be taken
  back.

### 4. Where guardrails sit

```
authenticate → resolve alias → model policy + residency → input guardrails
  → RPM → cache lookup (on the REDACTED request) → budget/TPM/lease → provider
  → output restore + output scan → response
```

- The cache key is computed from the **redacted** request (what's actually sent), and
  cached responses are stored **before** restore. So a cached entry never contains
  restored originals, and restore runs again, fresh, on every hit. Test this.
- A blocked request isn't provider-bound: no usage record. It's still recorded in
  metrics and logs.

### 5. Data residency

- Add `region` to every catalogue model entry: one of `us`, `eu`, `cn`, `global`,
  `unknown`. **Verify** each value from the provider's official documentation (data
  processing location or privacy terms), with the URL and date. Where the docs don't
  guarantee a location, use `global` or `unknown`. Never guess a flattering region.
- Org and team **residency policies** list allowed regions. The same storage, CLI,
  audit, caching and strictest-wins rules apply (team ∩ org). No policy = all regions.
- Residency is enforced **inside the step 9 policy engine**, on the concrete resolved
  model, so aliases, weighted routes and fallbacks are all filtered by it. A denied
  model → 403 `model_not_allowed`, with a message saying the model's region isn't
  permitted.
- `/v1/models` hides models outside the allowed regions.

### 6. Visibility (never values)

- Metrics: `lgw_guardrail_findings_total{direction, detector, action}` (bounded labels).
- Logs: one `guardrail_findings` event per request, with detector types and counts only.
- Usage records: add `redaction_count` (nullable int) with a migration.
- Tracing: a `guardrails.input` / `guardrails.output` span with counts per detector type,
  and no values.
- A test proves no original value appears in logs, spans, metrics, the cache or usage
  records.

### 7. CLI

```bash
uv run gateway-admin set-guardrails <org> [--team T] --action email=redact --action card_number=block
uv run gateway-admin set-residency <org> [--team T] --allow-region us --allow-region eu
uv run gateway-admin show-guardrails <org> [--team T]   # effective action per detector and allowed regions
uv run gateway-admin clear-guardrails|clear-residency <org> [--team T]
```

## Tests required

1. A detector table: true and false positives for each detector (e.g. a 16-digit order
   ID failing Luhn is **not** a card).
2. **ReDoS:** adversarial inputs finish within a small time bound.
3. Consistent placeholders; restore in non-streaming; streaming restore with placeholders
   split across 2 and 3 chunks; the mapping never persisted anywhere.
4. Strictest-wins for guardrails and residency (org/team/default combinations).
5. Block → 400 with detector types, no values, no provider call, no usage record.
6. Default secret blocking, including our own `lgw_` key format.
7. Output scanning: non-streaming redact and block; streaming detect-only.
8. Cache interaction: the key uses the redacted request; stored entries contain no
   originals; restore runs on hits.
9. Residency: a direct model, an alias, a weighted route and a **fallback** to a
   disallowed region are all blocked; `/v1/models` is filtered.
10. The no-leak test across logs, spans, metrics, cache and usage records.
11. **Live:** ask a real model to repeat a sentence containing an email address. The
    provider receives `[EMAIL_1]` (assert the outgoing request with a transport spy),
    and the client receives the original email (`live`).
12. Before reporting, temporarily break each of these and confirm a test fails: (a) skip
    scanning tool results, (b) team policy loosening an org `block`, (c) compute the
    cache key before redaction, (d) drop the streaming hold-back buffer, (e) skip the
    residency check on fallback targets, (f) remove the Luhn check.

## Docs required

- **ADR 0020:** guardrail design (deterministic detectors, actions, strictest-wins,
  placement in the pipeline, ReDoS safety, the limits of pattern matching).
- **ADR 0021:** redaction with restore (in-memory mapping, streaming hold-back, and why
  output scanning on streams is detect-only) and data residency.
- **`docs/architecture.md`:** a "Step 11" section in plain language: redaction and
  restore (a translator who swaps names for codes before passing notes to a stranger,
  then swaps them back), why checksums cut false positives, what data residency means
  legally, and why pattern matching can't catch everything.
- **Threat model:** PII reaching providers, secrets in prompts, obfuscated PII that
  evades patterns (be honest), placeholder injection by users, residency bypass, and
  the restore mapping as sensitive in-memory data.
- **README:** the policies, CLI, error codes and regions table. **Roadmap:** step 11
  done, step 12 next.

## Out of scope

ML/NER-based PII detection (e.g. names and addresses; mention Presidio as a future
option), image or file scanning, prompt-injection detection, content moderation
categories, and per-key guardrails.

## Report back with

- Final output of the four gates and the db, redis and live tests (exact AGENTS.md
  commands).
- The catalogue region table with source URLs.
- The detector true/false-positive table your tests cover.
- Design as built, open decisions, tests changed, and `git log --oneline main..HEAD`.
