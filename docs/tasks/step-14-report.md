# Step 14 implementation report — 2026-09-30

## Outcome and scope

Implemented only in `/Users/udo/claude sessions/llm-gateway-providers`, branch
`feat/step-14-zai-nvidia-providers`, from main at 28168a1. The spec was the first
commit (`docs: add step 14 spec`). No main-folder, console, step 13b, guide-branch
or guide-worktree changes; no push or merge; no installs, uv sync or real-key use.

Built ZaiAdapter/NvidiaAdapter, provider names/settings/defaults/registry, sourced
catalogue entries, strict preserved-reasoning history, explicit unpriced periods,
Singapore residency/API discovery, respx/cost/live tests, ADR 0026, architecture,
README and roadmap. No dependencies or migrations added. New modules remain below
300 lines; no new module needs an over-400-line exception.

## Verification: actual commands and final output

| Command | Final output |
|---|---|
| `.venv/bin/ruff check .` | `All checks passed!` |
| `.venv/bin/ruff format --check .` | `357 files already formatted` |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | `0 errors, 0 warnings, 0 informations` |
| `env -u GATEWAY_TEST_DATABASE_URL -u GATEWAY_TEST_REDIS_URL .venv/bin/pytest -p no:cacheprovider -q` | `1216 passed, 162 skipped, 37 deselected in 24.54s` |
| `env -u GATEWAY_PROVIDERS__ZAI__API_KEY -u GATEWAY_PROVIDERS__NVIDIA__API_KEY .venv/bin/pytest -p no:cacheprovider -q -m live tests/live/test_providers.py -k 'zai or nvidia'` | `6 skipped, 12 deselected in 0.01s` |

This tests **skipping** the live suite, not live provider success. Normal tests
block real provider HTTP with respx. Infrastructure variables were unset for the
normal run to reserve shared DB/Redis tests for the end, as requested.

At the end, `docker ps` identified the existing project as `llm-gateway`.
Reused the shared containers without recreating/restarting them, using only this
worktree's compose file:

```bash
ADMIN_CONSOLE_SESSION_SECRET=synthetic-compose-interpolation-only docker compose --env-file /dev/null -p llm-gateway up -d --no-recreate postgres redis
```

Output: `Container llm-gateway-postgres-1 Running` and
`Container llm-gateway-redis-1 Running`. The value is a synthetic interpolation
placeholder, not a real secret; no console service was started.

Then ran these **sequentially**, DB first:

```bash
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/postgres' .venv/bin/pytest -p no:cacheprovider -q -m db
# 97 passed, 11 skipped, 1307 deselected in 32.77s

GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/postgres' GATEWAY_TEST_REDIS_URL=redis://127.0.0.1:6379/14 .venv/bin/pytest -p no:cacheprovider -q -m redis
# 65 passed, 1350 deselected in 56.04s
```

The 11 DB skips require Redis too; they ran in the subsequent Redis invocation.
The existing fixture creates/migrates/drops `gateway_test_<uuid>` databases, never
the main `gateway` database. Redis used database 14, never 15. Neither suite
failed or needed an interference retry. Earlier offline runs caught stale
five-region/four-provider expectations and one import-order/type-check issue;
these were corrected before the final successful checks above.

## Official fact verification

All sources below were opened by the agent on 2026-09-30. The trial PDF required
curl plus the PDF reader: webfetch itself returned
`Unsupported fetched file content type: application/pdf`; the subsequent official
PDF download/read succeeded. No facts were invented from missing content.

### Z.ai (international Model API)

| Spec fact / check | Status and official evidence |
|---|---|
| Base URL `https://api.z.ai/api/paas/v4`, chat path `/chat/completions`; Coding Plan is separate | **Verified**: https://docs.z.ai/guides/overview/quick-start, curl and OpenAI SDK examples. No `/v1` substitution. |
| `glm-5.3-flash` exact model ID | **Verified**: https://docs.z.ai/guides/vlm/glm-5.3-flash and https://docs.z.ai/api-reference/llm/chat-completion. |
| Flash USD/1M input 0.15, cached input 0.03, output 0.50 | **Verified**: https://docs.z.ai/guides/overview/pricing. List rates used, not a discount. |
| Launch promotion ended 2026-09-09 | **reviewer-verified 2026-09-30, not re-verified by agent**: https://docs.z.ai/guides/overview/pricing currently shows list prices, not promotion history. Also marked in the adapter docstring. |
| FlashX 0.37 / 0.075 / 1.25 and GLM-5.3 1.4 / 0.26 / 4.4 | **Verified**: same pricing page; exact IDs verified by the Flash guide and chat reference. All three catalogued. Account access remains unverified. |
| Singapore operation / customer-data processing | **Verified**: https://docs.z.ai/legal-agreement/privacy-policy, specifically **API DPA section 3** says Customer Data is generally processed in Singapore. Not just a registered-address inference or an exclusive guarantee. |
| Developer role | **Verified role enum**: https://docs.z.ai/api-reference/llm/chat-completion lists system/user/assistant/tool, not developer; translated to system. Native developer support was not verified. |
| max_tokens vs max_completion_tokens | **Verified max_tokens** in the chat reference; **max_completion_tokens support not verified**, no explicit non-support statement found. Forward both unchanged rather than guessing a translation. |
| stream_options.include_usage | **Not verified as supported** in the chat reference/https://docs.z.ai/guides/capabilities/streaming. Forward/ask anyway under the undocumented-parameter rule. Final-chunk usage is **verified** independently, including the combined finish/usage chunk shape. |
| response_format/json_schema | **Verified restriction**: chat reference enum text/json_object excludes json_schema. Structured JSON capability does not imply JSON Schema output support. |
| Unsupported parameters | **Verified** json_schema and GLM-5.3-family thinking.type disabled restrictions in chat reference / Flash guide. Stop prose says one stop word while schema says maxItems=4; do not guess a new local limit. Undocumented penalties/logprobs/etc. are forwarded. |
| Reasoning/thinking output | **Verified** message.reasoning_content in chat reference and delta.reasoning_content in streaming guide. Both already canonical; no tag extraction. clear_thinking=false history preservation is documented in the chat reference. |
| Cached-token usage | **Verified** prompt_tokens_details.cached_tokens in chat reference/streaming example; preserved as canonical cached input, not added again to total input. |
| Embeddings endpoint | **Verified absence from the international documentation inventory**: https://docs.z.ai/llms.txt. Rejected locally; no claims about BigModel China. |

### NVIDIA API catalogue / hosted Kimi-K3

| Spec fact / check | Status and official evidence |
|---|---|
| Base URL `https://integrate.api.nvidia.com/v1`, chat path | **Verified**: https://build.nvidia.com/moonshotai/kimi-k3 and https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer. |
| Exact lowercase `moonshotai/kimi-k3` | **Verified** in the infer API's default and requestJson examples. **Difference**: the generated build-page prototype has empty model placeholders, so that prototype alone cannot confirm casing. |
| 1,048,576-token context | **Verified**: https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3 and build page. This is model documentation, not a gateway tokenizer/enforced context limit. |
| reasoning_effort low/high/max | **Verified** in model page and infer enum; thinking always enabled is stated on the model page. |
| Tools and structured output | **Verified** model/build-page capabilities; tools also appear in infer schema. Exact response_format handling remains a live check because the request schema omits it; omission is not a reason to reject it. |
| Complete prior assistant history, including reasoning and tool calls | **Verified** model page and infer request reasoning_content field. Previous gateway behaviour dropped reasoning; now a strict optional string is preserved for NVIDIA/Z.ai only. |
| Trial service, no production contract | **Verified** model page's linked [Trial Terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), sections 1.2 and 1.4. Production requires a separate paid NIM/partner subscription. |
| Free prototyping / no per-token charge | **Not established** by the official terms. **Difference**: section 1.4 permits deducted credits and purchase of more credits. Do not infer $0 from “trial”; catalogue is explicitly unpriced. |
| Rate-limited | **Use limits verified** by terms 1.1/1.4; a numeric limit or specifically requests-per-time guarantee was **not verified** on these pages. No invented quota. |
| Global geography | **Verified**: “Deployment Geography: Global” on https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3 and build page; catalogue uses global. |
| Usage in responses/streams | **Verified** infer UsageInfo and response/stream schemas, plus include_usage description. Canonical prompt/completion/total fields are preserved. Actual account stream usage remains untested live. |
| Reasoning output fields | **Verified** model-page reasoning_content requirement and build-page reasoning extraction example. **Difference**: infer response/delta schemas only list role/content and lag that feature. Preserve canonical reasoning_content when returned, do not manufacture it. |
| Cached tokens | **Alternate NVIDIA cache shape not verified** in the infer reference. Preserve canonical cached_tokens if returned; otherwise unknown. No speculative normalisation. |
| Unsupported parameters | **Verified** infer temperature description: top_p, presence_penalty, frequency_penalty, n are “fixed by the model and are not exposed”; reject all supplied values including null/n=1. System/assistant object-list content is explicitly unsupported. |
| Developer/token-limit spelling | **Verified** role enum system/user/assistant/tool and max_tokens; translate developer. max_completion_tokens is **not verified** and not explicitly prohibited; forward unchanged. |
| Embeddings | **No Kimi embeddings endpoint documented** in its endpoint reference; adapter rejects embeddings. Other NVIDIA-hosted models/endpoints remain out of scope. |
| Request ID | **Verified** NVCF-REQID in infer response headers; recorded without exposing credentials. |

## Parameter contract, decisions and alias proposal

- **Translated:** developer → system on both; model routing removes only the gateway
  prefix, responses/chunks gain that prefix. No token-limit translation. NVIDIA
  flat-message/problem-detail errors now retain provider rejection messages; 401/403
  still become sanitized gateway 502, verified by shared respx tests.
- **Z.ai rejected:** embeddings, response_format.json_schema,
  thinking.type=disabled for glm-5.3/glm-5.3-flash/glm-5.3-flashx.
- **NVIDIA rejected:** embeddings, top_p, presence_penalty, frequency_penalty, n,
  system/assistant content arrays (developer arrays become system first).
- **Forwarded:** all other canonical fields after strict schema validation and only
  the serving provider's namespaced options. Both max_tokens and
  max_completion_tokens, reasoning_effort, tools, unknown options, usage requests,
  and NVIDIA response_format/tool_choice pass unchanged. Model-specific ranges and
  undocumented restrictions are left to provider 4xx responses. Reasoning/history
  and usage fields already match canonical names. Never parse think tags or invent
  cache/reasoning counts. Other providers keep dropping assistant reasoning history.
- **Unpriced decision:** effective-dated explicit flag, never a guessed rate. Valid
  usage gets NULL-cost/unpriced receipts, separate CLI counts and known TPM tokens.
  No usage remains usage_missing. Weighted aliases exclude unpriced models; direct
  requests/listing remain available. USD budget accounting cannot quantify unknown
  trial-credit costs; token/rate/concurrency controls still apply.
- **Region:** sg is a real reviewed category, accepted by CLI/admin/policy parsing.
  EU-only teams cannot use it. `allowed_regions` is ARRAY(String) in
  tenants/models.py and migration 0008; no enum migration. The new cost status is
  String(32), also no migration.
- **Region endpoint:** add regions to `/admin/v1/me` from REGIONS, rather than add a
  new route. Existing authenticated bootstrap serves both roles, adds no new
  authorization surface or DB query, and lets step 13b read the authoritative list.
  Tests cover exact list, accepted sg, invalid-region error and EU routing denial.
- **Settings:** standard key/base-URL settings, disabled without a key; reuse
  today's global connect/read/write/pool timeout settings. No speculative nested
  per-provider timeout settings were introduced.
- **Alias proposal (not implemented):** after live quality/latency and entitlement
  validation, consider fast weights **Groq 80 / DeepSeek 10 / Z.ai Flash 10**. This
  is a small attributable trial and adds provider diversity; Flash output is more
  expensive than Groq 20B (0.50 vs 0.30 USD/1M), but cheaper than DeepSeek's peak
  output (1.20). “Flash” is not measured latency evidence. Singapore residency and
  sending data to a new company need explicit product/legal approval. Keep smart
  and embed unchanged. Current fast/smart/embed entries are untouched.

## Limits and outstanding checks

No objection to the binding design decisions. The spec explicitly permits
unpriced NVIDIA when the terms do not justify zero; that fallback was necessary.
The reviewer must run the opt-in two-provider chat/stream smoke tests with real
keys/network. Live entitlements, response-field emission, actual billing/credits,
timeouts/latency and account rate limits were not measured. Physical processing
location cannot be proven by API success. GLM promotion history was not re-verified.
No spec requirement was knowingly omitted; the requested exact NVIDIA Decimal
cost test is instead an explicit refusal/NULL-cost test because inventing a price
would contradict the spec. Console changes and paid production endpoints remain
out of scope. No remote CI run is claimed.

Run `git log --oneline main..HEAD` for the commit list; the final handoff includes
its actual output, including the documentation/report commit.
