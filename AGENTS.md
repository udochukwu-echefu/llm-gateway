# Working on this repository

Instructions for coding agents (and humans). Read this file and `docs/architecture.md`
before changing anything. Task specs live in `docs/tasks/`.

## What this is

A multi-tenant LLM gateway: one OpenAI-compatible API in front of several model providers.
It's a portfolio project built to production standards. The code is read by reviewers and
interviewers, so clarity matters as much as correctness.

## Commands

```bash
uv sync                      # install
uv run pytest -q             # tests (must not touch the network)
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pyright               # strict type check
docker compose up -d         # start local Postgres
GATEWAY_TEST_DATABASE_URL='postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway' uv run pytest -q -m db
```

## Definition of done (every task)

All of these must hold before you report a task as finished:

1. `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright` (0 errors) and
   `uv run pytest -q` all pass. Paste their final output lines in your report.
2. Every new behaviour has a test, and each test would fail if the behaviour broke.
   Test behaviour through the HTTP API where practical, not private helpers.
3. No test makes a real network call. Mock providers with `respx`.
4. `docs/architecture.md` gains a plain-language section for the step. The owner is
   learning, so explain *why* in simple words and define any new term.
5. Significant design decisions get an ADR in `docs/adr/` (copy the existing format).
6. `docs/roadmap.md` and `README.md` are updated if behaviour or configuration changed.
7. Your report lists what you built, every decision the spec left open and what you chose,
   anything you could not verify, and any spec requirement you did not meet.
8. Start Postgres with `docker compose up -d` and run database tests with
   `GATEWAY_TEST_DATABASE_URL` set; report that result separately.

## Code organisation

Keep the code easy to navigate: someone new should find anything in under a minute.

**Files**
- One module, one job. If you need "and" to describe a module, split it.
- Aim for under 300 lines per module. Over 400 is a signal to split, so explain in your
  report why a file needs to be that long. Never create a catch-all module
  (`utils.py`, `helpers.py`, `misc.py`); name modules after what they do.
- Group by feature/layer, following the existing layout:

  ```
  src/llm_gateway/
    api/        HTTP endpoints only: parse, call the layer below, shape the response
    schemas/    Pydantic models of the canonical format; no I/O
    providers/  one module per provider, plus shared base/registry code
    *.py        cross-cutting pieces (config, logging, errors, middleware, context, sse)
  ```

- Dependencies point downward only: `api` → `providers` → `schemas`. Never import from
  `api` in a lower layer, and avoid import cycles.

**Functions and classes**
- A function does one thing and is short enough to read without scrolling (roughly under
  40 lines). Pull out a well-named helper instead of adding comments that split a long
  function into sections.
- Names say what something is or does (`resolve_provider`, not `handle` or `process`).
  Booleans read as questions (`supports_embeddings`).
- Keep nesting shallow: return early on errors instead of deep `if/else` chains.
- Keep private helpers (`_name`) below the public function that uses them, so a file
  reads top-down.
- No duplicated logic: if two providers need the same code, it goes in the shared base.
  But don't build an abstraction for a single use.

**Tests**
- Test files mirror what they test: `tests/providers/test_groq.py` for
  `providers/groq.py`, `tests/api/...` for endpoints. Shared fixtures go in `conftest.py`.
- Each test checks one behaviour and is named after it
  (`test_unknown_provider_returns_404`), with arrange / act / assert separated by blank
  lines.
- Older tests in `tests/` predate this layout. New tests follow it. If you move old tests
  into the new layout, do it in its own `refactor(tests):` commit that changes no test
  behaviour.
- Shared test data (sample requests, responses, stream chunks) lives in one fixtures
  module, not copied between files.

**Commits**
- One logical change per commit, e.g. a refactor that moves code, separate from the
  commit that changes behaviour. A reviewer should be able to read each commit on its own.

## Code rules

- "Not documented is not the same as not supported." Reject a parameter before the
  network call only when official provider docs say it is unsupported, deprecated, or
  has no effect, or when the endpoint does not exist. Otherwise forward it unchanged;
  provider 4xx errors and messages pass through per ADR 0002.

- Python 3.13, fully typed, pyright strict. No `# type: ignore`. A
  `# pyright: ignore[rule]` needs a comment saying why.
- Match the existing style: small modules, docstrings that explain *why*, and comments
  only where the reason isn't obvious from the code.
- Pydantic models: requests strict (`RequestModel`), provider responses tolerant
  (`ResponseModel`). See ADR 0003.
- Every error a client can see uses the OpenAI error envelope via `GatewayError`, with a
  stable `code`. Follow the mapping in ADR 0002.
- Never log prompts, completions, embeddings or API keys. Log metadata only (model,
  provider, status, timings, token counts).
- Settings come from `GATEWAY_*` environment variables through `config.py`. Invalid
  configuration must fail at startup.
- Don't add a dependency unless the spec allows it or you justify it in your report.

## Git

- Work on the branch named in the task spec, created from `main`.
- Small commits in Conventional Commits style (`feat:`, `fix:`, `refactor:`, `test:`,
  `docs:`). Each commit should pass the tests.
- Never commit `.env` or any real key. Never push, merge, or rewrite history on `main`.

## Security

- Provider keys are secrets: `SecretStr` in settings, never in logs, errors or test output.
- A provider's 401/403 must never reach the client as a 401/403 (ADR 0002).
- Treat all client input as untrusted. Validate before any network call.
