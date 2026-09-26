# LLM Gateway

One OpenAI-compatible API in front of many model providers, built for company use:
central keys, per-team limits and budgets, cost tracking, failover and audit logs.

> **Status: step 1 of 12.** A streaming pass-through proxy to one provider. There is no
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
  -d '{"model": "llama-3.3-70b-versatile", "stream": true,
       "messages": [{"role": "user", "content": "Say hi in five words"}]}'
```

Or point any OpenAI SDK at it:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="unused-until-step-4")
```

## Development

```bash
uv run pytest            # tests (no network: providers are mocked)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # strict type check
```

CI runs all four on every push, then builds the Docker image and smoke-tests it.

## Configuration

All settings are environment variables prefixed `GATEWAY_` (see `src/llm_gateway/config.py`).

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_UPSTREAM_API_KEY` | required | Provider API key |
| `GATEWAY_UPSTREAM_BASE_URL` | Groq | Any OpenAI-compatible base URL |
| `GATEWAY_READ_TIMEOUT_S` | 60 | Longest silence allowed between chunks |
| `GATEWAY_MAX_REQUEST_BYTES` | 2 MiB | Larger bodies are rejected with 413 |
| `GATEWAY_LOG_FORMAT` | `json` | `json` or `console` |

## Docs

- [Architecture, in plain language](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- Decisions: [ADR 0001: OpenAI-compatible API](docs/adr/0001-openai-compatible-api.md),
  [ADR 0002: error mapping](docs/adr/0002-upstream-error-mapping.md)
