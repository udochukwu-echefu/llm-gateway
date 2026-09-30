# Step 14: Two more providers, Z.ai (GLM) and NVIDIA (hosted Kimi)

- **Branch:** `feat/step-14-zai-nvidia-providers` (from `main` at 28168a1)
- **Worktree:** `/Users/udo/claude sessions/llm-gateway-providers`. Work **only** here. The main
  folder `/Users/udo/claude sessions/llm-gateway` is in use by another agent on the step 13b
  branch; never check out, commit to or run migrations from that folder.
- **Read first:** `AGENTS.md`, `docs/architecture.md` (Steps 3, 5, 9, 11), ADRs 0002-0005,
  0008, 0016-0021, `catalog/models.toml`, every module in `src/llm_gateway/providers/`
  (especially `openai_compat.py`, `deepseek.py`, `groq.py`), and this spec.

## Goal

The gateway routes to Groq, DeepSeek, Gemini and OpenAI. The owner now has a **Z.ai** key
(GLM models) and will soon have an **NVIDIA API catalog** key (build.nvidia.com), which hosts
Moonshot's **Kimi K3** among many other models. Add both as providers, the same way the
existing ones were added, so that:

- `zai/glm-5.3-flash` works for chat (streaming and non-streaming);
- `nvidia/moonshotai/kimi-k3` works for chat (streaming and non-streaming). NVIDIA is a
  *host*: its model IDs contain their own slash, exactly like `groq/openai/gpt-oss-20b`;
- both appear in the catalogue with sourced prices and regions, usage is recorded and priced,
  and policies (models, residency, guardrails) apply to them like any other provider.

## Facts gathered by the reviewer (2026-09-30), to verify against the official pages

The reviewer checked these on 2026-09-30. **Verify each against the official page before
relying on it**, cite the page in the adapter docstring and the catalogue (like `deepseek.py`
and `groq.py` do), and report any difference. Never fill a gap with a guess: if something
cannot be verified, say so, and choose the safe behaviour (forward unknown parameters; mark
an unknown region `unknown`; leave a price unpriced rather than invented).

**Z.ai (international platform, not Zhipu BigModel China)**
- Base URL: `https://api.z.ai/api/paas/v4` (chat at `/chat/completions`), per
  https://docs.z.ai/guides/overview/quick-start. Note the path is `/api/paas/v4`, not `/v1`.
  The separate "GLM Coding Plan" endpoint is out of scope.
- Model ID: `glm-5.3-flash`.
- Price (USD per 1M tokens), https://docs.z.ai/guides/overview/pricing: input 0.15,
  cached input 0.03, output 0.50 (a launch promotion ended 2026-09-09; use list price).
  The same page lists `glm-5.3-flashx` (0.37 / 0.075 / 1.25) and `glm-5.3` (1.4 / 0.26 / 4.4).
  Catalogue all three chat models if verified; the owner's key may not have access to all of
  them, which is fine.
- Region: https://docs.z.ai/legal-agreement/privacy-policy states the API service is operated
  from Singapore, and customer data is generally processed in Singapore. See "a new region"
  below.
- Check the chat API reference for: `developer` role support, `max_tokens` vs
  `max_completion_tokens`, `stream_options.include_usage`, response_format/json_schema,
  unsupported parameters, reasoning/"thinking" output fields, cached-token usage fields, and
  whether an embeddings endpoint exists (if none is documented for this platform, embeddings
  are rejected, like Groq).

**NVIDIA API catalog (build.nvidia.com, "integrate" API)**
- Base URL: `https://integrate.api.nvidia.com/v1` (OpenAI-compatible
  `/chat/completions`), per https://build.nvidia.com/moonshotai/kimi-k3 and
  https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3.
- Model ID: `moonshotai/kimi-k3` (confirm the exact casing in the official API example).
- Documented: 1,048,576-token context; `reasoning_effort` (low/high/max); tools; structured
  output. Multi-turn and tool-call requests "must return the complete prior assistant message
  to the model, including reasoning content and tool calls". Check whether the gateway's
  strict request schema lets a client send back the assistant's reasoning content (ADR 0005).
  If it does not, decide how to support it without weakening strict validation for other
  fields, and record the decision in the ADR.
- Pricing: the hosted endpoint is a **trial service** under the NVIDIA API Trial Terms of
  Service (free for prototyping, rate-limited, not a production contract). Catalogue it with
  a price of 0 **only if** the official terms support "no per-token charge"; cite them, add a
  catalogue comment and a README note that production use needs a paid NVIDIA NIM or partner
  endpoint. If the terms are unclear, leave it unpriced.
- Region: the model page lists "Deployment Geography: Global" → `global`.
- Check the API reference for usage in responses and streams, reasoning output fields, and
  unsupported parameters.

## Decisions already made (binding; object in your report if you disagree)

### 1. Adapters

- `providers/zai.py` (`ZaiAdapter`) and `providers/nvidia.py` (`NvidiaAdapter`), each built on
  `OpenAICompatibleAdapter`, with a docstring citing the official evidence in the same style
  as `deepseek.py`: base URL, what is translated, what is rejected (with quotes), what is
  forwarded, how reasoning and cached tokens are normalised.
- Follow AGENTS.md's rule: "Not documented is not the same as not supported." Reject a
  parameter only when the official docs say it is unsupported; otherwise forward it.
- Provider names `zai` and `nvidia` (added to `ProviderName`, the registry, defaults and
  settings). Environment variables: `GATEWAY_PROVIDERS__ZAI__API_KEY`,
  `GATEWAY_PROVIDERS__NVIDIA__API_KEY` (plus the usual optional base-URL/timeout settings).
  A provider without a key stays disabled, exactly like today.
- Each provider gets its own connection pool (bulkhead) and circuit breaker, as the existing
  ones do. No shared state between them.

### 2. A new region: `sg` (Singapore)

The residency feature knows `us`, `eu`, `cn`, `global` and `unknown`. Z.ai documents
Singapore, and labelling that `global` or `unknown` would be wrong. Add `sg`:
- `Region` in `guardrails/policy.py`, its validation message, the admin API and CLI help,
  README, architecture doc and threat model.
- Regions are stored as plain strings (no migration needed). Confirm that and say so.
- Tests: `sg` is accepted by residency policies; a team allowed only `eu` cannot use a `sg`
  model; the error lists `sg` among valid regions.
- The console's residency editor (step 13b, being built in parallel) must read the list of
  regions from the API rather than hard-code five. Don't edit the console on this branch;
  just make sure the region list is available from the API: add a `regions` list to the
  existing `/admin/v1/me` response, or to a small read-only endpoint if that is cleaner.
  Justify the choice in your report.

### 3. Catalogue and aliases

- Catalogue entries for the verified models, with `region`, `region_source_url`,
  `region_checked_on`, effective-dated prices, `source_url` and `checked_on`, like the
  existing entries.
- **Don't change existing aliases** (`fast`, `smart`, `embed`): changing where traffic goes is
  a product decision. Propose, in the report, whether GLM should join `fast` and at what
  weight, with reasoning.

### 4. Tests (no real network in the normal suite)

- Adapter tests with `respx`, mirroring the existing provider tests: request translation,
  rejected parameters, streaming with usage, reasoning normalisation, error mapping (a
  provider 401/403 becomes a gateway 502 per ADR 0002), and model IDs containing a slash
  (`nvidia/moonshotai/kimi-k3`).
- Cost tests: usage from each provider is priced exactly with the catalogue prices (Decimal).
- Opt-in live tests (`pytest -m live`), skipped without keys, one short non-streaming and one
  streaming call per provider. You probably can't run them in your sandbox (no network or
  keys); the reviewer will run them with the owner's keys.

## Docs and CI

- **ADR 0026:** adding Z.ai and NVIDIA: host-vs-model-maker naming, the `sg` region, trial
  pricing, reasoning round-tripping for Kimi, the "not documented is not the same as not
  supported" evidence.
- **`docs/architecture.md`:** a "Step 14" section in plain language: what a model *host* is
  vs a model *maker* (analogy: a cinema shows films made by studios; NVIDIA is the cinema,
  Moonshot the studio), why each provider keeps its own pool and breaker, and why data
  residency needed a new region.
- **README:** provider list, environment variables, the trial-service note for NVIDIA.
  **Roadmap:** add step 14.
- CI stays green.

## Out of scope

Other NVIDIA-hosted models (they become one catalogue entry each later), Z.ai's Coding Plan
endpoint, the Zhipu China platform, Moonshot's own platform, embeddings on these providers
unless officially documented, changing aliases, console changes.

## Report back with

- Final output of ruff, format, pyright, pytest, and the db and redis suites (sequentially).
- For each provider: every fact above marked verified or not (with the official URL), and any
  difference from the reviewer's notes.
- The rejected / translated / forwarded parameter lists, the reasoning handling, the `sg`
  region decision and the regions-list endpoint choice, and the alias proposal.
- Anything you could not verify, and `git log --oneline main..HEAD`.
