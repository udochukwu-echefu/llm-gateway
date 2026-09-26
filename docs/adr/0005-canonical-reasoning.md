# ADR 0005: A canonical reasoning output field

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

DeepSeek returns `reasoning_content`; Groq returns `reasoning`. Clients should not
need provider-specific code to read separate reasoning output.

## Decision

Add optional, nullable `reasoning_content` to response messages and stream deltas.
Adapters normalize documented separate reasoning fields to this name. Groq's original
field is removed after translation; an existing canonical field takes precedence.
Do not extract `<think>` tags from content or manufacture reasoning that was not returned.
Assistant request history continues to drop output-only fields (ADR 0003).

## Consequences

Clients have one typed field for reasoning. Providers without a verified separate
reasoning representation retain their response extras without speculative conversion.

## Alternatives considered

- Keep provider-specific names: rejected because every client must translate them.
- Parse reasoning out of ordinary text: rejected because quoted tags are ambiguous.
