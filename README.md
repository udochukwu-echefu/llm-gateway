# LLM Gateway

One OpenAI-compatible API in front of many model providers, built for company use:
central keys, per-team limits and budgets, cost tracking, failover and audit logs.

> **Status: step 3 of 12.** Chat completions and embeddings in OpenAI's format, validated
> end to end, routed per request to Groq, DeepSeek, Gemini or OpenAI. There is no
> client authentication yet, so run it only on your own machine. See the
> [roadmap](docs/roadmap.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env        # then put your provider key in .env
uv run uvicorn llm_gateway.main:create_app --factory --no-access-log --reload
```

Call it like OpenAI:

```bash
curl -N http://127.0.0.1:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model": "groq/llama-3.3-70b-versatile", "stream": true,
       "messages": [{"role": "user", "content": "Say hi in five words"}]}'
```

Or point any OpenAI SDK at it:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="unused-until-step-4")
```

Provider-only options go in `provider_options`, and only the serving provider's are sent:

```python
client.chat.completions.create(
    model="groq/openai/gpt-oss-20b",
    messages=[{"role": "user", "content": "hi"}],
    extra_body={"provider_options": {"groq": {"include_reasoning": False}}},
)
```

## Endpoints

| Endpoint | Notes |
|---|---|
| `POST /v1/chat/completions` | Streaming and non-streaming; optional features depend on provider and model |
| `POST /v1/embeddings` | Needs a provider that offers embeddings (Gemini or OpenAI; Groq and DeepSeek don't) |
| `GET /healthz` | Liveness |

## Development

```bash
uv run pytest            # tests (no network: providers are mocked)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # strict type check
uv run pytest -m live    # opt-in smoke calls, skipped for missing environment keys
```

CI runs all four on every push, then builds the Docker image and smoke-tests it.

Live tests read `GATEWAY_PROVIDERS__<PROVIDER>__API_KEY` from the process environment
(not `.env`), and optional matching `BASE_URL` overrides. They run one chat, one stream
with usage and, for Gemini/OpenAI, one embedding. The default suite deselects these tests
and blocks real provider HTTP requests.

## Configuration

All settings are environment variables prefixed `GATEWAY_` (see `src/llm_gateway/config.py`).

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_PROVIDERS__GROQ__API_KEY` | unset | Enable Groq |
| `GATEWAY_PROVIDERS__DEEPSEEK__API_KEY` | unset | Enable DeepSeek |
| `GATEWAY_PROVIDERS__GEMINI__API_KEY` | unset | Enable Gemini's OpenAI-compatible endpoint |
| `GATEWAY_PROVIDERS__OPENAI__API_KEY` | unset | Enable OpenAI |
| `GATEWAY_PROVIDERS__<PROVIDER>__BASE_URL` | provider default | Optional HTTP(S) endpoint override |
| `GATEWAY_READ_TIMEOUT_S` | 60 | Longest silence allowed between chunks |
| `GATEWAY_MAX_REQUEST_BYTES` | 2 MiB | Larger bodies are rejected with 413 |
| `GATEWAY_LOG_FORMAT` | `json` | `json` or `console` |

At least one nonempty key is required. Each enabled provider has its own connection pool;
timeout and pool-size settings are global. The old `GATEWAY_UPSTREAM_*` settings are removed.

Use `<provider>/<model>` in every request. Only the first slash is split:
`groq/openai/gpt-oss-120b` routes to Groq with model `openai/gpt-oss-120b`.
Unknown, unprefixed or unconfigured providers return `404 model_not_found`, listing
configured providers. Responses and stream chunks prefix the provider's returned model ID.

Unsupported parameters return `400 unsupported_parameter` before a provider call.
Developer instructions become system instructions on DeepSeek and Gemini. DeepSeek's
token limit is translated to `max_tokens` (supplying both limits is rejected).
Groq's separate `reasoning` output becomes `reasoning_content`, as on DeepSeek.
Capabilities are endpoint-level; models can have additional restrictions.

Defaults: Groq `https://api.groq.com/openai/v1`, DeepSeek `https://api.deepseek.com/v1`,
Gemini `https://generativelanguage.googleapis.com/v1beta/openai`, OpenAI `https://api.openai.com/v1`.
Verified documentation and conservative restrictions are recorded in each adapter's docstring.
In particular, Gemini's undocumented token-limit parameters are currently rejected.

## Docs

- [Architecture, in plain language](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- Decisions: [ADR 0001: OpenAI-compatible API](docs/adr/0001-openai-compatible-api.md),
  [ADR 0002: error mapping](docs/adr/0002-upstream-error-mapping.md),
  [ADR 0003: canonical schema](docs/adr/0003-canonical-schema.md),
  [ADR 0004: provider adapters](docs/adr/0004-provider-adapters.md),
  [ADR 0005: reasoning output](docs/adr/0005-canonical-reasoning.md)
