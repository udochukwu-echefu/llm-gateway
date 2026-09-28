# Step 11 implementation report

Implemented on `feat/step-11-guardrails`, created from `main`. The first commit is
`a609801 docs: add step 11 spec` and contains only the supplied task spec. Nothing
was pushed or merged. Required documents were read before implementation.

## Verification

Final local gate output (2026-09-28):

```text
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
260 files already formatted
$ uv run pyright
0 errors, 0 warnings, 0 informations
$ uv run pytest -q
904 passed, 95 skipped, 25 deselected in 17.56s
```

Database and Redis were run separately using the exact AGENTS.md commands:

```text
$ docker compose up -d
Container llm-gateway-redis-1 Started
Container llm-gateway-postgres-1 Started

$ GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
44 passed, 9 skipped, 971 deselected in 23.99s

$ GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run pytest -q -m redis
51 passed, 973 deselected in 12.17s
```

The nine db skips also require Redis, which the db-only command intentionally does not
configure; they pass in the separate Redis command. Docker stopped between work sessions:
an intermediate rerun had connection-refused setup errors. Starting Docker Desktop and
running `docker compose up -d` resolved them; final results above are after recovery.

Last live run (2026-09-27; later changes added offline tests/docs and conservative nested
option scanning, without changing the live email request path):

```text
$ uv run --env-file .env pytest -m live
2 failed, 13 passed, 10 skipped, 992 deselected in 46.23s
```

- The new email-redaction transport-spy test passed for **Groq, DeepSeek and Gemini**.
  It asserts the outbound body contains `[EMAIL_1]` and not the original example.com
  email, then asserts the client gets that email back. OpenAI skipped: no configured key.
- Failures: `tests/live/test_providers.py::test_live_chat[gemini]` and
  `tests/live/test_providers.py::test_live_stream_with_usage[gemini]`: Google HTTP **429**.
  No credential/model/quota workaround was used. Existing retry behaviour was retained.
- Other skips are unsupported embedding endpoints, provider-specific smoke tests and
  the missing OpenAI key. Live credentials were used only through existing secret settings;
  no real key value was printed, added to test data or committed.
- The first live spy run exposed an email-followed-by-period detector bug. It was fixed,
  covered by a regression test and verified by the passing spy rerun, not hidden as a skip.

## Catalogue regions

All sources were fetched from the providers' official documentation on **2026-09-27**.
The date and URL are also stored per model in `catalog/models.toml`.

| Model | Region | Source |
|---|---|---|
| `groq/openai/gpt-oss-20b` | `unknown` | https://console.groq.com/docs/your-data |
| `groq/openai/gpt-oss-120b` | `unknown` | https://console.groq.com/docs/your-data |
| `deepseek/deepseek-flash` | `cn` | https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html |
| `gemini/gemini-3.8-flash` | `global` | https://ai.google.dev/gemini-api/terms |
| `gemini/gemini-embedding-2` | `global` | https://ai.google.dev/gemini-api/terms |
| `openai/gpt-4.1-nano` | `global` | https://platform.openai.com/docs/guides/your-data |
| `openai/text-embedding-3-small` | `global` | https://platform.openai.com/docs/guides/your-data |

Groq's US retention statement does not guarantee US inference. DeepSeek explicitly says
collect/process/store in PRC. Gemini permits facilities worldwide; OpenAI's default global
endpoint has no processing constraint. No physical processing location was independently
verified; API responses cannot establish that. ADR 0021 explains scope and contractual limits.

## Detector test table

`tests/guardrails/test_detectors.py` checks positive spans and negative matches per type:

| Detector | Positive examples | Negative examples |
|---|---|---|
| `secret_api_key` | Artificial `sk-` + repeated `FAKE`; `gsk_`, `AIza`, `ghp_`, `AKIA` with repeated fake characters; fake `lgw_` with 12-char public ID and 43-char secret | Short/malformed example for each of those six prefixes |
| `secret_private_key` | Complete fake PRIVATE KEY block (base64 “FAKE”); DSA PRIVATE KEY block | Incomplete block with no END |
| `email` | `ada@example.com`, including followed by sentence punctuation | `ada@localhost` |
| `phone` | `+1 (415) 555-0100`; UK fictional mobile `07700 900123` | Five digits; twenty digits |
| `card_number` | Published test Visa `4242 4242 4242 4242` and `4111-1111-1111-1111` | Mutated checksum `4242 4242 4242 4243`; order ID `1234567890123456` |
| `iban` | Documented `GB82 WEST 1234 5698 7654 32`, also followed by uppercase prose | Changed checksum `GB83 WEST 1234 5698 7654 32` |
| `ip_address` | Reserved documentation addresses `192.0.2.1`, `2001:db8::1`; punctuation boundary | Invalid octet `999.0.2.1`; invalid IPv6 `2001:db8::gg` |

Adversarial cases: repeated `a@a.a@a`, 100 KB letter/digit runs, spaced digit runs and
repeated incomplete private-key headers. Every case must finish in under one second.
Shared HTTP fixtures contain only reserved-domain emails and documented/test payment data.

## Built design and open choices resolved

- Pure compiled-pattern scanner; immutable strictest-wins policies; migration 0008;
  audited CLI; existing bounded key cache; residency inside the step 9 policy engine.
- Request-scoped typed placeholders, collision reservation and single-pass restore;
  per-choice/per-field/per-tool streaming hold-back, preserving stream closure semantics.
- Cache fingerprints use redacted input; encrypted values contain pre-restore output;
  fresh mappings restore each hit. Output checks apply on hits using current policy.
- New nonstreaming output is scanned **before** restoring known input codes. This is
  necessary to implement useful restore without immediately re-masking supplied PII.
  New output masks use a separate `OUTPUT_` namespace. Output blocks keep paid usage.
- Set commands replace scope overrides; duplicate detector flags use the last supplied
  action. NULL inherits; clear removes overrides. Defaults still cannot be weakened.
- Overlapping redaction spans use earliest/longest; any blocking finding wins. Counts
  include every detector finding; usage `redaction_count` counts actual input replacements.
- All namespaced option text is conservatively scanned, including options for providers
  not selected. JSON tool arguments are decoded so unicode escapes cannot hide values.
- Missing region in older/custom catalogues defaults to `unknown`; every reviewed entry
  explicitly has its region, source and date. `unknown` and `global` are not wildcards.
- Forbidden fallback targets are skipped, preserving ADR 0016's original-provider error
  or 503 semantics rather than introducing a new fallback-time 403.
- Stream detection uses per-channel pre-restore text retained until close; delivery
  hold-back is bounded, but this separate detection copy grows with generated output.
  It is never persisted. Incremental detection is a future memory optimization.
- No new dependency. New production modules remain under 300 lines; no new or enlarged
  400-line production module needed an exception. Tests follow feature/layer directories.
- No objection to the binding decisions. Their limits are documented: pattern detection
  is not complete DLP, streams cannot retract output, and region declarations need contracts.

Unverified/limited: OpenAI live behaviour without a key; two Gemini quota-limited smoke
checks; physical inference locations; obfuscated/encoded PII, images/files/audio and integer
embedding tokens (no provider tokenizer). Python cannot securely erase immutable strings.
No implementation requirement was intentionally omitted; these boundaries are explicitly
documented rather than represented as complete protection.

## Tests changed

Added `tests/guardrails/` detector, policy, repository, restore and lifetime tests;
HTTP suites `test_guardrails_input.py`, `test_guardrails_output.py`,
`test_guardrails_stream_channels.py`, `test_guardrails_cache.py`, `test_residency.py`;
database receipt round-trip test `tests/usage/test_guardrail_count.py`; live transport spy
`tests/live/test_guardrails.py`. Shared fixtures were extended for tenant policy injection.
Existing tracing and metrics tests now require the new spans/counter/label names; no old
behaviour assertion was weakened. Baseline: 806 passed; final offline suite: 904 passed.

## Test 12: temporary break-and-revert evidence

Each mutation was applied alone, its targeted tests run, then reverted. After all six,
`git diff --exit-code` returned no differences; the full suite subsequently passed.

1. **Skip tool results:** return a tool-message dictionary without visiting content.
   Failed: `tests/api/test_guardrails_input.py::test_tool_results_are_scanned`.
   Result: **1 failed**.
2. **Team loosens organization:** return the team's action instead of taking the maximum.
   Failed:
   - `tests/api/test_guardrails_input.py::test_organization_block_cannot_be_loosened_by_team`
   - `tests/guardrails/test_policy.py::test_team_cannot_loosen_organization[allow-redact]`
   - `tests/guardrails/test_policy.py::test_team_cannot_loosen_organization[allow-block]`
   - `tests/guardrails/test_policy.py::test_team_cannot_loosen_organization[redact-block]`
   Result: **4 failed, 6 passed** (parameter IDs are team-org).
3. **Cache key before redaction:** pass the original request to cache-key construction,
   while the provider still receives the redacted request.
   Failed: `tests/api/test_guardrails_cache.py::test_cache_uses_redacted_request_and_restores_fresh_on_hit`.
   Result: **1 failed**.
4. **Remove streaming hold-back:** disable unfinished-prefix buffering.
   Failed:
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[content-parts0]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[content-parts1]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[content-parts2]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[reasoning_content-parts0]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[reasoning_content-parts1]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[reasoning_content-parts2]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[refusal-parts0]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[refusal-parts1]`
   - `tests/api/test_guardrails_output.py::test_stream_restores_split_placeholders[refusal-parts2]`
   - `tests/guardrails/test_redaction.py::test_holdback_only_keeps_valid_prefix_and_flushes_at_end`
   Result: **10 failed, 6 passed**.
5. **Skip fallback region check:** substitute the permitted primary's region for the
   fallback's actual region, retaining its model-pattern checks.
   Failed: `tests/api/test_residency.py::test_fallback_cannot_bypass_residency`.
   Result: **1 failed**.
6. **Remove Luhn:** accept card-shaped candidates without checksum validation.
   Failed both card rows of `tests/guardrails/test_detectors.py::test_detector_true_and_false_positives`:
   - `[card_number-4242 4242 4242 4242-4242 4242 4242 4243]`
   - `[card_number-4111-1111-1111-1111-1234567890123456]`
   Result: **2 failed, 22 deselected**.

## Implementation commits

```text
ebacb7c test: verify redaction cleanup and persisted usage counts
5b23336 fix: harden guardrail text boundaries and verify live restore
f6955d3 feat: redact and restore guarded requests across cache and streams
4f698af feat: persist audited guardrail policies and enforce model residency
a88c4c9 feat: add deterministic guardrail detectors and action policies
a609801 docs: add step 11 spec
```

The final documentation commit adds this report, ADRs 0020/0021, architecture, threat model,
README and roadmap updates. The final response includes `git log --oneline main..HEAD`
after that commit, avoiding a self-referential commit hash in this file.
