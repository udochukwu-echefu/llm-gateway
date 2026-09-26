# ADR 0004: Canonical provider adapters with isolated connection pools

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

One configured upstream cannot serve requests to several providers. Their similar APIs
still differ in supported parameters and response fields. The HTTP endpoints should not
need to know those details.

## Decision

- Clients choose `<provider>/<model>`. Split only the first slash, preserve the rest,
  and prefix the provider's returned model ID in every response and chunk. Missing,
  unknown, disabled or empty model destinations return `404 model_not_found` with the
  configured provider names. There is no model catalog or alias resolution.
- `ProviderAdapter` exposes canonical `chat`, `open_chat_stream` and `embed` operations.
  `ChatStream` yields canonical chunks and must be closed by its owner. Adapters own
  JSON validation, SSE decoding and transport/status errors. The API owns usage recording,
  usage hiding, SSE encoding and terminal success/error events.
- Shared wire behavior lives in `openai_compat.py`, with single-purpose `transport.py`
  and `stream.py` modules. Four thin adapters declare frozen capabilities in one place.
- Unsupported parameters (including explicitly supplied nulls) fail locally with
  `400 unsupported_parameter`. Translate developer instructions to system when needed;
  translate DeepSeek's completion limit to `max_tokens`, rejecting two non-null limits.
  Explicit null is treated as absence for the limit conflict. Verified supported native
  spellings are preserved. Gemini token-limit translation is not verified, so both spellings
  are rejected rather than silently losing a limit.
- Capabilities describe endpoints, not every model. Model-specific restrictions remain
  provider errors. Arbitrary namespaced provider options remain an explicit pass-through.
- A nested settings block enables a provider exactly when its key is non-null. Empty keys
  are configuration errors. Validate HTTP(S) URLs, disallow embedded credentials/query/
  fragments, and require at least one enabled provider. Defaults come from adapter classes.
- Each enabled provider gets one lifespan-owned client with its own pool. `AsyncExitStack`
  closes already-created clients on partial startup failure too. Timeout and size limits
  are shared settings. Stream shutdown is cancellation-shielded, including disconnects.
- Record provider/model and verified request-ID headers before checking status. Only
  OpenAI's `x-request-id` was verified; other adapters record `None`, not a guessed header.
- Preserve existing stream termination behavior: explicit `[DONE]` succeeds; EOF after a
  finish reason succeeds; otherwise EOF is truncation. Decode/transport failures become
  `GatewayError` and the API sends one terminal error event without a success marker.
- Normalize separate reasoning output as described in [ADR 0005](0005-canonical-reasoning.md).

## Consequences

Provider-specific wire data never crosses the adapter interface. A slow provider cannot
exhaust another provider's pool. A fifth compatible provider can reuse the contract suite
by registering its adapter. Some undocumented features are conservatively unavailable.

Official documentation was checked on 2026-09-26; sources are in adapter docstrings.
Groq's current embedded OpenAPI schema documents developer and streamed usage even though
its Python message union lags behind. DeepSeek's current reference explicitly drops penalties.
DeepSeek's required `/v1` default is retained despite its current quickstart documenting
only the root URL; configure the documented root URL if the alias is unavailable.

Unverified features: Gemini developer/native token-limit spellings, temperature, top_p,
stop, seed, log probabilities/bias, penalties, parallel-tool flag, message names, user and
safety identifiers; multiple choices beyond its n=1 example; embedding token IDs,
dimensions, encoding format and user; separate reasoning output. Gemini developer maps
to documented system instructions; other listed request features are rejected.
Groq embeddings/safety_identifier and DeepSeek embeddings/n/seed/logit_bias/
parallel_tool_calls/service_tier/user/safety_identifier are not documented and are rejected.
Gemini/DeepSeek/Groq request-ID response headers were not verified and remain unset.

## Alternatives considered

- One shared HTTP pool: rejected because a stalled provider could starve all others.
- Native Gemini API: deferred by scope; use its OpenAI-compatible endpoint.
- Accept undocumented fields optimistically: rejected for canonical parameters; that can
  silently ignore client intent. Namespaced provider options remain the escape hatch.
