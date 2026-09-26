# ADR 0003: A strict canonical schema, with a namespace for provider-specific options

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

Step 1 forwarded the client's bytes without reading them. Later steps need to understand
requests and responses: adapters translate them (step 3), cost tracking reads token usage
(step 5), routing reads the model (step 9), guardrails read the messages (step 11).

We have to decide how strict to be, and where provider-only features (Groq's
`reasoning_format`, DeepSeek's `thinking`, ...) should go.

## Decision

1. **Requests are strict.** Pydantic models of OpenAI's Chat Completions and Embeddings
   requests, with unknown fields and loosely typed values rejected (400). This matches
   OpenAI, which also rejects unrecognised arguments.
   - **One exception:** assistant messages in the history ignore unknown fields. Clients
     commonly send a previous response message back unchanged, and it carries output-only
     fields such as `annotations` or `reasoning_content`.
2. **Responses are tolerant.** We check the fields we rely on (`id`, `model`, `choices`,
   `usage`, ...). Unknown fields are kept and passed on, so a provider adding a field never
   breaks traffic. A response missing required fields becomes a 502
   `upstream_invalid_response`.
3. **Provider-specific options go in `provider_options.<provider>`.** Only the options for
   the provider actually serving the request are sent. Keys that would overwrite a standard
   field (`messages`, `max_tokens`, ...) are rejected.
4. **The gateway always asks for streamed usage** (`stream_options.include_usage`) and
   removes the usage chunk again if the client didn't ask for it.
5. **Streams are parsed and checked chunk by chunk.** A stream always ends with `[DONE]` or
   with an error event, never with a silent cut-off.

## Consequences

- Typos (`temprature`) fail loudly instead of being ignored.
- When fallback (step 7) moves a request to another provider, options meant for the first
  provider don't break the second one.
- Because provider options can't overwrite standard fields, they can't be used to get
  around checks on those fields (budgets, guardrails).
- A brand-new OpenAI parameter is rejected until we add it to the schema. It can be passed
  through `provider_options.openai` in the meantime.
- Parsing every streamed chunk costs a few microseconds each. That's negligible next to
  model latency, and step 12's load test will confirm it.
- Provider-specific reasoning fields (`reasoning_content`, `reasoning`) pass through as
  they are for now. Step 3 adapters will normalise them.

## Alternatives considered

- **Pass unknown top-level fields through** (what OpenAI SDKs' `extra_body` does). Rejected:
  a field meant for one provider breaks another after fallback, and typos pass silently.
- **Validate responses strictly.** Rejected: our traffic would break whenever a provider
  adds a field.
