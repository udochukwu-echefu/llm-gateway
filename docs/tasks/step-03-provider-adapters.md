# Step 3: Provider adapters

- **Branch:** `feat/step-3-provider-adapters` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, ADRs 0001–0003,
  `src/llm_gateway/api/chat.py`, `src/llm_gateway/upstream.py`

## Goal

Today the gateway talks to **one** provider chosen by configuration. After this step it
talks to **Groq, DeepSeek, Gemini and OpenAI at the same time**. The provider is chosen per
request from the model name, and each provider has an adapter that hides its quirks behind
the canonical format.

## Decisions already made (do not change them without saying why in your report)

### 1. Model naming: `<provider>/<model>`

- Clients send e.g. `"model": "groq/llama-3.3-70b-versatile"` or
  `"model": "gemini/gemini-2.5-flash"`.
- Split on the **first** `/` only. Provider model IDs can contain slashes
  (`groq/openai/gpt-oss-120b` means provider `groq`, model `openai/gpt-oss-120b`).
- Unknown provider, missing prefix, or a provider with no API key configured → **404**,
  type `invalid_request_error`, code `model_not_found`. The message must say what's wrong
  (e.g. "Provider 'openai' is not configured on this gateway") and list the configured
  providers. It must not reveal key material.
- Responses and streamed chunks report `model` as `<provider>/<model the provider returned>`.

### 2. Configuration: one block per provider

Use pydantic-settings nested models with `env_nested_delimiter="__"`:

```
GATEWAY_PROVIDERS__GROQ__API_KEY=...
GATEWAY_PROVIDERS__DEEPSEEK__API_KEY=...
GATEWAY_PROVIDERS__GEMINI__API_KEY=...
GATEWAY_PROVIDERS__OPENAI__API_KEY=...
GATEWAY_PROVIDERS__GROQ__BASE_URL=...        # optional, each has a correct default
```

- A provider is **enabled if and only if its API key is set**. At least one must be
  enabled, or startup fails with a clear message.
- Remove `upstream_provider`, `upstream_base_url` and `upstream_api_key`. Update
  `.env.example` and `README.md`.
- The timeout and pool settings stay global for now.

### 3. One HTTP client per provider

Each enabled provider gets its own `httpx.AsyncClient` (its own connection pool), created
in the app lifespan and closed on shutdown. This is the **bulkhead** pattern: a slow
provider can use up only its own connections, not everyone's. Explain it in the
architecture doc.

### 4. Layering

```
api/chat.py, api/embeddings.py    HTTP concerns: parse the request, resolve the provider,
                                  encode SSE, hide unrequested usage, end every stream
                                  with [DONE] or an error event
        │  canonical models only
        ▼
providers/registry.py             "groq/llama..." → (adapter, "llama...")
providers/base.py                 ProviderAdapter protocol, ChatStream, Capabilities
providers/openai_compat.py        shared HTTP, error mapping (moved from upstream.py),
                                  SSE parsing into ChatCompletionChunk objects
providers/groq.py, deepseek.py,   thin subclasses: base URL, capabilities, translations
gemini.py, openai.py
```

Required shape (you may refine names and details, but keep the ideas):

```python
class ChatStream(Protocol):
    """Canonical chunks from one provider stream. Must be closed (it holds a connection)."""

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]: ...
    async def aclose(self) -> None: ...


class ProviderAdapter(Protocol):
    name: ProviderName
    capabilities: Capabilities

    async def chat(self, request: ChatCompletionRequest, model: str) -> ChatCompletion: ...
    async def open_chat_stream(self, request: ChatCompletionRequest, model: str) -> ChatStream: ...
    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse: ...
```

- Adapters receive and return **canonical models only**. JSON and SSE bytes never leave
  the adapter.
- `open_chat_stream` must raise `GatewayError` for HTTP error statuses **before** the
  client response starts, as today, so clients still get proper 4xx/5xx statuses.
- Failures after streaming starts are raised from the iterator as `GatewayError`. The API
  layer turns them into an SSE error event.
- Keep the guarantee that the provider connection is closed when the client disconnects.
  The existing disconnect test must still pass, adapted to the new structure.
- `upstream.py` is deleted or reduced to what is still genuinely shared. No dead code.

### 5. Capabilities and translations

Each adapter declares its capabilities in **one place** (a frozen dataclass or similar):
supports embeddings, supports `stream_options.include_usage`, supports the `developer`
role, supports `max_completion_tokens`, and a set of unsupported request parameters.

- A request that uses an unsupported feature is rejected with **400**, code
  `unsupported_parameter`, and a message naming the parameter and provider, **before any
  network call**. Example: embeddings on Groq or DeepSeek.
- Where a translation is safe, translate instead of rejecting:
  - `developer` role → `system` for providers without `developer` support.
  - `max_completion_tokens` → `max_tokens` for providers without it (reject if both are set).
- **Reasoning output:** add an optional `reasoning_content: str | None` to the canonical
  `ResponseMessage` and `Delta`. Map provider-specific reasoning fields onto it (DeepSeek
  already uses `reasoning_content`; check what Groq returns). Record this in an ADR.
- **Verify every capability and translation against the provider's current official
  docs.** Put the doc URL and the date you checked in the adapter's docstring. If you
  can't verify something, choose the conservative option and list it in your report.
  Don't guess silently.

Default base URLs (verify these too):

| Provider | Base URL |
|---|---|
| groq | `https://api.groq.com/openai/v1` |
| deepseek | `https://api.deepseek.com/v1` |
| gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| openai | `https://api.openai.com/v1` |

Gemini goes through its OpenAI-compatible endpoint in this step. A native Gemini adapter
is a separate later task.

### 6. Observability

- `annotate(provider=..., model=...)` on every request, so the access log shows which
  provider served it.
- Keep recording the provider's request ID. Each adapter knows which response header holds
  it (they may differ). Use `None` if a provider has none.

## Tests required

1. **Contract tests, parametrized over all four adapters.** The same canonical request
   through each adapter must produce correct canonical results for non-streaming,
   streaming, usage recording, error-status mapping, transport errors, and disconnect
   cleanup. Adding a fifth provider later should mean adding one parameter.
2. **Per-adapter translation tests:** `developer` → `system`, `max_completion_tokens` →
   `max_tokens`, reasoning field mapping, and rejection of unsupported parameters with no
   network call made.
3. **Registry and config tests:** `provider/model` parsing including slashes inside the
   model ID; unknown, unprefixed and unconfigured providers; startup failure with no
   providers; only enabled providers get HTTP clients.
4. **`provider_options`:** the serving provider's options are sent and others are dropped,
   now that the provider comes from the model name.
5. **Live smoke tests** in `tests/live/`, marked `@pytest.mark.live`, **skipped by
   default** (register the marker and deselect it in `pyproject.toml`). For each provider
   whose key is in the environment: one non-streaming chat, one streaming chat with usage,
   and one embedding where supported. Run them with `uv run pytest -m live`. They must
   skip cleanly, not fail, when a key is missing.
6. All existing tests pass, updated only where behaviour intentionally changed (for
   example model names now need a prefix). Say in your report which tests you changed and why.

## Docs required

- ADR 0004: the adapter interface, `<provider>/<model>` naming, capability handling, and
  per-provider connection pools.
- ADR 0005 (or part of 0004): the canonical `reasoning_content` field.
- `docs/architecture.md`: a "Step 3" section in plain language. Explain what an adapter
  is (use an analogy), the bulkhead idea, why capabilities are checked before the network
  call, and how a request now flows through the layers.
- Update `README.md` (configuration, model naming, a curl example) and `docs/roadmap.md`
  (step 3 done, step 4 next).

## Out of scope (don't build these)

Native Gemini API, retries or fallback, model aliases or a model catalog, cost
calculation, client authentication, a `/v1/models` endpoint, new dependencies other than
test-only ones.

## Report back with

- The final output lines of ruff, the format check, pyright and pytest.
- A short summary of the design as built, with file list.
- Every decision this spec left open and what you chose.
- Every capability or translation you could not verify against official docs.
- Tests you changed or deleted, and why.
- The commit list (`git log --oneline main..HEAD`).
