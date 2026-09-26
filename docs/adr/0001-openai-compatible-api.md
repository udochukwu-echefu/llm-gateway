# ADR 0001: Expose an OpenAI-compatible API

- **Status:** Accepted
- **Date:** 2026-09-25

## Context

The gateway needs one request/response format that every client uses, whatever provider
serves the request. We could design our own, or adopt an existing one.

## Decision

Expose OpenAI's Chat Completions shape (`POST /v1/chat/completions`, the same JSON fields,
SSE streaming, and the `{"error": {...}}` envelope). Every error the gateway itself produces
uses that envelope too, including 404s and validation errors.

## Consequences

- Existing apps adopt the gateway by changing their SDK's base URL. OpenAI's SDKs, LangChain,
  LlamaIndex and most tools work unchanged.
- Groq, DeepSeek and Gemini already offer OpenAI-compatible endpoints, so step 1 can target
  any of them with configuration alone.
- Features that exist only on one provider (for example Anthropic's prompt caching
  controls) don't fit the format. Step 2 will define how provider-specific fields pass
  through.
- We follow OpenAI's schema changes rather than controlling our own.

## Alternatives considered

- **Our own schema:** full control, but every client needs a custom SDK. Rejected.
- **OpenAI's newer Responses API:** less widely supported by other providers and tools today.
  We can add it later as a second endpoint.
