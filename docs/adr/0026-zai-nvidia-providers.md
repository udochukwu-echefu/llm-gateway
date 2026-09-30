# ADR 0026: Z.ai and NVIDIA hosts, preserved reasoning and explicit unknown prices

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

GLM is served by Z.ai's international Model API. NVIDIA's API catalogue hosts
Moonshot's Kimi-K3: the company receiving the prompt is not necessarily the
company that made the model. The routing prefix must identify the host, because
credentials, outages and privacy terms belong to that destination.

Kimi requires previous assistant reasoning in multi-turn/tool-call history, but
ADR 0005 deliberately dropped that output-only field. NVIDIA's trial terms also
do not establish a zero per-token price. Assuming zero would hide unknown spend.

## Decision

- Register `zai` and `nvidia` as optional key-enabled providers on the shared
  `OpenAICompatibleAdapter`. Preserve first-slash routing, so
  `nvidia/moonshotai/kimi-k3` sends `moonshotai/kimi-k3` to NVIDIA. Each provider
  has its own lifespan HTTP pool, retry budget and circuit breaker, using the
  existing global timeout/pool settings. No dependencies are added.
- Z.ai defaults to `https://api.z.ai/api/paas/v4`, not `/v1`, the Coding Plan
  endpoint, or BigModel China. NVIDIA defaults to
  `https://integrate.api.nvidia.com/v1`. Keys use SecretStr and the usual secret
  store. Missing keys leave providers disabled. NVIDIA's documented NVCF-REQID
  header supplies the upstream request ID; Z.ai uses x-request-id if present.
- Translate developer to system from each reference's role enum. Both token-limit
  spellings pass unchanged: `max_tokens` is documented, but omission of
  `max_completion_tokens` is not a statement of non-support. This follows the
  ADR 0004 review amendment: **not documented is not the same as not supported**.
- Reject Z.ai json_schema, because the response-format enum is text/json_object,
  and `thinking.type=disabled` on the three reviewed GLM-5.3 models, because
  thinking "can only be enabled". Reject NVIDIA top_p, n (even 1/null), and both
  penalties: they are "fixed by the model and are not exposed". Reject object-list
  content for NVIDIA system/assistant messages (including translated developer),
  explicitly unsupported by its reference. Other fields/options pass unchanged;
  model-specific restrictions remain provider errors. No international Z.ai
  embeddings endpoint is in its documentation index; no Kimi embeddings endpoint
  is documented. Both adapters reject embeddings.
- Add a strict `str | None` reasoning_content field to assistant request history.
  Preserve it only when serving Z.ai or NVIDIA; older providers retain their
  dropping behaviour. Other fields keep their existing validation, including the
  intentional assistant-only ignored extras. This narrowly supersedes ADR 0005
  and supports Z.ai clear_thinking=false as well as Kimi's required tool loop.
  Canonical serialization, guardrail scanning/redaction, cache fingerprints and
  fallback translation all see the field. Reasoning stays sensitive content,
  never logged or put on usage receipts. Output reasoning/cache usage already use
  canonical fields; no think-tag parsing or fabricated token breakdowns.
- Add `sg` for Singapore. Z.ai's **API DPA section 3**, not just its headquarters,
  says Customer Data is generally processed in Singapore. This is a reviewed
  routing label, not an exclusive-location guarantee or legal certification.
  Regions remain plain string arrays (`0008_guardrails.py`, tenants/models.py);
  cost status is also a string. No database migration is needed.
- Add `regions` to authenticated `GET /admin/v1/me`, sourced from REGIONS. Both
  admin roles can learn the same valid values during existing identity bootstrap.
  This avoids another auth/authorization route and gives the parallel console
  editor one authoritative list. No console files are edited on this branch.
- Catalogue all three verified Z.ai models with list input/cache/output rates
  effective 2026-09-30. Catalogue NVIDIA Kimi with an effective-dated explicit
  `unpriced=true` period carrying its terms source/check date, **no token prices**.
  PricePeriod rejects missing rates unless explicitly unpriced and rejects prices
  mixed with that flag. compute_cost refuses an unpriced period. Successful calls
  with usage store `cost_status=unpriced`, NULL cost and known token counts;
  missing usage/failed attempts retain the existing distinct statuses. CLI reports
  count unpriced separately. Reviewed unpriced models are directly callable and
  listable, but excluded from weighted alias availability. No existing alias or
  fallback changes. Cache hits still cost zero, with unknown savings for an
  unpriced source; unknown-cost provider calls must not become zero-cost receipts.
- Extend shared transport message parsing for documented NVIDIA flat message and
  RFC 7807 problem-detail errors as well as the existing nested error shape.
  Authentication/server errors remain sanitized per ADR 0002.

## Evidence checked 2026-09-30

| Fact | Official source / finding |
|---|---|
| Z.ai URL | https://docs.z.ai/guides/overview/quick-start |
| GLM Flash/FlashX IDs and preserved thinking | https://docs.z.ai/guides/vlm/glm-5.3-flash and https://docs.z.ai/api-reference/llm/chat-completion |
| GLM list rates | https://docs.z.ai/guides/overview/pricing: Flash 0.15/0.03/0.50; FlashX 0.37/0.075/1.25; GLM-5.3 1.4/0.26/4.4 USD/1M |
| Z.ai Singapore | https://docs.z.ai/legal-agreement/privacy-policy, API DPA section 3 |
| Z.ai streamed reasoning, usage/cache fields | https://docs.z.ai/guides/capabilities/streaming; include_usage is not explicitly documented, so forwarded without a support guarantee |
| NVIDIA exact model ID / URL / stream options / usage / exclusions | https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer |
| Kimi context 1,048,576, reasoning_effort low/high/max, tools, structured output, complete history, Global | https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3 and https://build.nvidia.com/moonshotai/kimi-k3 |
| NVIDIA trial pricing | [Trial Terms PDF](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), sections 1.2/1.4: trial only, credit deductions and possible purchased credits; not a no-per-token-charge guarantee |

The reviewer's GLM promotion end date (2026-09-09) is **reviewer-verified
2026-09-30, not re-verified by agent**; today's pricing table supplies list rates
but no promotion history. NVIDIA's generated build-page example has empty model
placeholders; its official infer example confirms the exact lowercase ID. The
response/delta schemas lag the model card's reasoning feature; preserve the
canonical field when returned, without claiming a live observation. No alternate
NVIDIA cached-token shape or numeric trial rate limit was verified.

## Consequences

Production NVIDIA use needs a paid NIM or partner endpoint and newly reviewed
prices/regions. The terms prohibit trial production and confidential/sensitive
inputs (sections 2.6/4.3); deterministic guardrails cannot certify compliance.
Use synthetic, nonsensitive trial prompts. USD budgets can count only known
costs, not NVIDIA credit consumption; RPM, TPM, concurrency and model/residency
policies still apply. Do not describe these requests as free or budget-enforced
actual spend. Operators must review changed endpoints and contractual terms.

Live smoke tests are opt-in, environment-key-gated, with low reasoning effort
and 1024 output-token limits for these two providers. Mocked tests prove protocol
behaviour, not account entitlements, physical inference location or live billing.

## Alternatives considered

- Prefix `moonshot` for NVIDIA: wrong credential/privacy/failure boundary.
- Set NVIDIA prices to zero: unsupported by the trial terms; conceals uncertainty.
- Exclude Kimi entirely for missing prices: prevents the explicitly requested
  prototype; explicit unknown pricing permits honest accounting without guessing.
- Forward reasoning to every provider or allow arbitrary request extras: broader
  compatibility/validation change than needed.
- Label Singapore global/unknown: contradicts the reviewed API processing source.
- Add a regions-only endpoint: extra route with no benefit over identity bootstrap.
