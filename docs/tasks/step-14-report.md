# Step 14 implementation report — 2026-09-30

## Timeout and live-history follow-up: items 7–8 (latest)

Step 14's first merge already completed as `12cf60a`. The owner then authorized
these additions on the retained `feat/step-14-zai-nvidia-providers` worktree.
The checks in this section supersede earlier gate counts below. Separate commits:

- `283a07b feat(providers): support per-provider timeout overrides`
- `c6a61f8 test(live): cover NVIDIA GLM and slow Kimi history replay`

### Built and chosen

- Optional positive, finite connect/read/write/pool overrides in ProviderSettings,
  exposed as `GATEWAY_PROVIDERS__<PROVIDER>__<PHASE>_TIMEOUT_S`. Unset uses globals,
  with one reviewed exception: NVIDIA's effective default read timeout is **300 s**.
  Explicit provider settings win. Other providers keep their global timeout values.
  A small typed timeout object is shared by pool construction and lease validation
  so the guard cannot accidentally validate different values from those used by HTTPX.
- Lease TTL must exceed the **largest combined effective timeout of an enabled
  provider**. Disabled providers do not raise the floor; independently largest phases
  from different providers are not added together. NVIDIA defaults total **320 s**
  (connect 5 + read 300 + write 10 + pool 5), below the existing **900 s** lease TTL.
  Validation runs again after secret-store resolution exposes enabled file-backed
  providers, before any provider pool is created. Tests cover all four overrides,
  startup failures, disabled providers, split maxima and secret-store enablement.
- The spec left the independent 60-second request deadline open. **It remains
  unchanged**, rather than silently relaxing every request when NVIDIA is enabled.
  README explicitly requires e.g. `GATEWAY_RESILIENCE__DEADLINE_S=330` for queued
  NVIDIA development. A 300-second read timeout alone cannot bypass a 60-second
  overall deadline. No `.env` change was made for the owner.
- `retry_read_timeouts=false` stays the default. The existing policy also forbids
  automatic fallback for a transport ReadTimeout: a potentially charged three-minute
  wait gets one attempt only. Approved fallback for a retryable upstream timeout,
  such as HTTP 504, gets only the remaining request deadline. Tests cover fallback
  with remaining time, no fallback after exhaustion, and cancellation of a stalled
  fallback rather than resetting the deadline.
- Respx tests cover delayed first chunks with NVIDIA's 300-second read metadata and
  a simulated **180.7 s** queue-inclusive TTFB under the longer explicit deadline.
  The test does not pretend to sleep/measure three minutes. A Redis test holds the
  first chunk, waits for an actual lease-renewal event using an accelerated test
  TTL, confirms admission remains held, then releases the stream and checks cleanup.
  Admission heartbeats begin before headers/first byte; SSE hold-back is text-length
  bounded and adds no separate short first-byte timer.
- The disconnect test now covers both the initial pending POST and a pending poll:
  the local upstream coroutine is cancelled, no response headers are sent, and the
  request receives a client-disconnected receipt. **Remote NVIDIA job deletion cannot
  be guaranteed**: the checked official status API has no documented cancel operation.
  The requested “no queued work left running” is verified locally, not promised for
  NVIDIA's remote queue. This is the sole unverifiable portion of that requirement.
- Added NVIDIA **z-ai/glm-5.3-flash** immediately after Kimi in the live model list,
  with distinct provider/model test IDs. NVIDIA live profiles use **330 s** gateway
  deadlines and **360 s** client/per-call asyncio bounds. Other live profiles keep
  60 s gateway deadlines. No timeout library or other dependency was added.
- Added a dedicated `live`/`slow` Kimi multi-turn test: require actual nonempty
  reasoning_content, replay the complete first assistant message in turn two and
  check both unpriced receipts. Without a key it skips; a non-Kimi explicit model
  override also skips rather than claiming Kimi coverage. The same test flow runs
  offline with respx and checks the exact second upstream history. Existing provider
  model overrides keep their semantics; the NVIDIA override applies to both smoke
  rows, so it should be unset when exercising both default models.
- README, ADR 0026 and architecture explain: **free-tier queueing can take minutes;
  not suitable for interactive production traffic**. Roadmap includes per-provider
  timeouts. No alias, migration, dependency, production endpoint or budget-policy
  change was made. New modules remain below 300 lines; no 400-line exception is needed.

### Reviewer-provided live evidence, not new agent measurements

Owner's NVIDIA key, 2026-09-30:

| Target | Reviewer observation |
|---|---|
| NVIDIA moonshotai/kimi-k3 | HTTP 200 after **180.7 s** for three words; **21 completion tokens, 7 reasoning tokens**. Queue-inclusive latency, not generation speed. |
| NVIDIA z-ai/glm-5.3-flash | HTTP 200 in **16 s**, reasoning_content and completion_tokens_details.reasoning_tokens; NVCF-REQID and NVCF-STATUS fulfilled. |
| Z.ai direct | HTTP 429, business code **1113**, insufficient balance/no account credit. The sanitized non-retryable account mapping is already merged. |

The agent did not read/use the key, call a live provider, verify free-credit allowance,
measure live Kimi multi-turn behaviour, or prove removal of remote queued jobs. NVIDIA
prices remain unpriced: successful development access is not evidence of a universal
zero token price. Existing official trial/region/parameter evidence remains in ADR 0026.

### All final gates after items 7–8

| Command | Final output |
|---|---|
| `.venv/bin/ruff check .` | `All checks passed!` |
| `.venv/bin/ruff format --check .` | `382 files already formatted` |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | `0 errors, 0 warnings, 0 informations` |
| Normal pytest, DB/Redis test URLs unset | `1348 passed, 197 skipped, 44 deselected in 27.95s` |
| DB pytest `-m db`, Redis URL unset | `131 passed, 11 skipped, 1447 deselected in 32.97s` |
| Redis pytest `-m redis`, database **14** | `66 passed, 1523 deselected in 58.47s` |
| NVIDIA key-unset live selection | `7 skipped, 15 deselected in 0.06s` |
| Key-unset `live and slow` Kimi history selection | `1 skipped, 21 deselected in 0.01s` |
| Console `npm run format:check` | `All matched files use Prettier code style!` |
| Console `npm run lint` | `eslint .`, exit 0 |
| Console `npm run typecheck` | `tsc --noEmit`, exit 0 |
| Console `npm test` | `Test Files 14 passed (14)`; `Tests 64 passed (64)` |
| Console `npm run build` | `Compiled successfully in 1100ms`; TypeScript/static generation finished; exit 0 |
| Full console `npm run test:e2e`, port **3300** | `19 passed (44.9s)` |
| Shared browser-response scanner | `No-leak scan total: 1358 browser responses; 1 permitted key-creation response; zero leaks.` |

All non-live provider requests were mocked with respx. The live skip checks unset
the relevant process keys explicitly; they prove skipping, **not live success**.
No test downloaded a browser or used an installed timeout plugin. Normal Python
and console gates preceded infrastructure suites. DB, Redis, then e2e ran sequentially
with no failures or interference retries. Reused containers with
`docker compose --env-file /dev/null -p llm-gateway up -d --no-recreate postgres redis`;
both reported Running. The PostgreSQL maintenance URL ended in `/postgres`; fixtures
created/migrated/dropped disposable databases, never the main `gateway` database.
Redis/e2e used database 14. The 11 Redis-dependent DB skips ran in the Redis suite.

No installs, push, guide-branch/worktree changes, screenshots, real provider calls,
or reads/prints/modifications of the worktree's ignored `.env` were made. The final
handoff records the subsequent authorized follow-up merge and actual main log.

## Review follow-up and NVIDIA additions (current)

The sections below this follow-up preserve the **initial, pre-review report**.
This follow-up supersedes its no-console/no-merge scope and Kimi-only NVIDIA scope.
The owner authorized integration of main's step 13b (81ac5bf), console validation,
the four review changes and additions 5–6. Main was clean when first checked.
Only README, architecture, roadmap and threat-model conflicted; both steps were
kept in order, without renumbering ADR 0025/0026. No guide branch/worktree was touched.
The worktree's `.env` was never read, printed or modified. No packages were installed:
Python used the existing `.venv`; Node 24.15.0 reused a local copy of main's installed
console dependencies after checking the package/lockfiles were identical.

### Error evidence and choices

- https://docs.z.ai/api-reference/api-code quotes `1113` as
  **"Insufficient balance or no resource package. Please recharge."**
  `1302` is **"Rate limit reached for requests"**; `1305` is
  **"The service may be temporarily overloaded, please try again later"**.
  Account/billing/allowance codes **1113, 1308, 1309, 1310, 1311, 1313–1321**
  return generic `502 upstream_account_error`, one attempt, no Retry-After and no
  private provider account message. A metadata-only operator log says to check
  billing/quota/entitlements. Authentication codes retain sanitized 401/403 mapping;
  real rate limits, temporary overload and unknown codes retain the shared path.
  The complete classification and official quotations are in the Z.ai docstring.
- NVIDIA's Kimi reference, FAQ and quickstart did not establish analogous 429
  business codes. The later GLM references **do** document HTTP **402 Payment
  Required**, with **"You have reached your limit of credits."** in their
  PaymentRequiredError example. NVIDIA 402 now uses the same generic non-retryable
  account error; no speculative 429 code/message matching was added.
- `/admin/v1/catalog` now returns the same authoritative `regions` as `/me`, for
  either admin role, and correctly marks explicit unpriced periods as not priced.
  The real browser test offers `sg`, saves it, verifies three Singapore GLM models
  and reloads the saved choice. No duplicated console region enum was needed.
- README, ADR 0026 and the threat model state plainly: **budgets cannot limit an
  unpriced model because its cost is unknown**. Budget-limited teams must restrict
  such models with model policy, e.g. allow only priced destinations, not `nvidia/*`.

### Official NVIDIA GLM and queued-request evidence

- https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-infer and
  https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash-infer have official
  request examples using exact IDs **z-ai/glm-5.3** and **z-ai/glm-5.3-flash**.
  https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3 and
  https://build.nvidia.com/z-ai/glm-5-3-flash say **Global** and link the existing
  NVIDIA Trial Terms. Both NVIDIA-hosted GLMs are catalogued as Global/unpriced;
  Z.ai's direct Singapore/pricing evidence does not transfer between hosts.
- Both GLM infer references document top_p and both penalties, unlike Kimi.
  Kimi's fixed sampling and non-user content-array restrictions now apply only
  to `moonshotai/kimi-k3`. Other absent fields remain forwarded; arbitrary string
  roles in the GLM reference preserve developer rather than importing Kimi's enum.
  Models remain directly callable/listable and excluded from weighted aliases.
  No alias or fallback entries changed.
- https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer explicitly
  lists integrate 202: **"Result is pending. Client should poll using the requestId."**
  NVCF-REQID is **"requestId required for pooling"** [sic].
  https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-statuspolling documents
  authenticated **GET https://integrate.api.nvidia.com/v1/status/{requestId}**,
  UUID request IDs, 202 pending and **200 application/json**.
  Therefore the integrate endpoint cannot truthfully be called universally synchronous.
- Implemented paced **nonstreaming Kimi** polling under the existing single total
  deadline. Request IDs cannot alter the host/path; no untrusted Location is followed.
  HTTP disconnect cancels pre-response work, including a pending poll. Every poll
  shares the original receipt and cannot resubmit inference after a poll or result-body
  failure, even with read-timeout retries enabled. Accepted jobs without usage stay
  `usage_missing`, not rejected/zero-cost. No remote cancellation API is documented.
- The status reference documents JSON only, and GLM references supply no queued
  polling protocol. Do not invent SSE polling or claim an undocumented synchronous
  guarantee: GLM/streaming 202 returns clear retryable
  `502 upstream_pending_unsupported`, never an empty client 202. Bounded retries of
  these unsupported queued modes may create extra accepted jobs; this residual risk
  and the lack of remote cancellation are documented in the threat model.
- The merged demo seeder originally attempted to compute numeric costs for unpriced
  periods. The first DB gate caught this (`1 failed, 130 passed, 11 skipped`). Fixed
  the seeder and strengthened its DB assertions: known NVIDIA tokens retain unpriced
  NULL cost; missing usage stays distinct; cache hits cost zero with unknown savings.

### Final validation after all code changes

| Command | Final output |
|---|---|
| `.venv/bin/ruff check .` | `All checks passed!` |
| `.venv/bin/ruff format --check .` | `375 files already formatted` |
| `.venv/bin/pyright --pythonpath .venv/bin/python` | `0 errors, 0 warnings, 0 informations` |
| `env -u GATEWAY_TEST_DATABASE_URL -u GATEWAY_TEST_REDIS_URL .venv/bin/pytest -p no:cacheprovider -q` | `1299 passed, 196 skipped, 37 deselected in 28.67s` |
| DB pytest `-m db`, Redis URL unset | `131 passed, 11 skipped, 1390 deselected in 36.08s` |
| Redis pytest `-m redis`, Redis database **14** | `65 passed, 1467 deselected in 59.92s` |
| Console `npm run format:check` | `All matched files use Prettier code style!` |
| Console `npm run lint` | `eslint .`, exit 0 |
| Console `npm run typecheck` | `tsc --noEmit`, exit 0 |
| Console `npm test` | `Test Files 14 passed (14)`; `Tests 64 passed (64)` |
| Console `npm run build` | `Compiled successfully in 3.5s`; TypeScript/static generation completed; dynamic routes built, exit 0 |
| Console full `npm run test:e2e`, port **3300** | `19 passed (49.5s)` |
| Shared e2e no-leak scanner | `No-leak scan total: 1358 browser responses; 1 permitted key-creation response; zero leaks.` |
| `git diff --check` | Exit 0, no output |

Database/Redis/e2e ran sequentially in that order, after normal Python checks.
Started/reused infrastructure with
`docker compose --env-file /dev/null -p llm-gateway up -d --no-recreate postgres redis`:
both containers reported Running; no secret interpolation was needed after 13b.
The pytest maintenance connection was
`postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/postgres`, never a
migration of the main `gateway` database. The 11 DB skips ran in the Redis suite.
E2e used the same maintenance connection, `CONSOLE_TEST_REDIS_URL=redis://127.0.0.1:6379/14`
and `CONSOLE_TEST_PORT=3300`, creating/dropping its own disposable database.
The production console build supplied only the documented synthetic e2e admin URL,
origin and session secret. No provider live calls, screenshots, browser downloads,
remote CI or push were performed. The reviewer reported live Z.ai calls and the 1113 account error;
the agent does not claim new live NVIDIA entitlements, free-credit allowance,
billing, response emission, polling occurrence or latency validation.

All requested changes are implemented; paid production endpoints and verified
NVIDIA account billing remain outside this task. The final handoff records the
authorized main merge result and actual `git log --oneline -3 main` after merging.

## Initial report (historical; superseded where noted above)

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
