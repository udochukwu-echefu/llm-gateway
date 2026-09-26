# Step 4: Tenants, virtual API keys and a secret store

- **Branch:** `feat/step-4-tenants-and-keys` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs, this spec
- **Needs:** Docker running locally (Postgres for tests)

## Goal

Today anyone who can reach the gateway can spend the company's provider credits. After
this step:

1. Every `/v1/*` request needs a **gateway-issued API key** that belongs to a team inside
   an organisation (the tenant).
2. Keys are stored so that **a database leak does not leak usable keys**.
3. Provider keys and the gateway's own secrets come from a **secret store** abstraction,
   not directly from settings.

## Decisions already made (binding; object in your report if you disagree)

### 1. Data model (Postgres)

```
organizations  id (uuid pk), name (unique), created_at
teams          id (uuid pk), organization_id (fk), name, created_at,
               unique (organization_id, name)
api_keys       id (uuid pk), team_id (fk), key_id (text, unique, indexed),
               secret_hash (bytea), name, created_at, expires_at (nullable),
               revoked_at (nullable)
```

- Nothing is ever hard-deleted. Revoking a key sets `revoked_at`, so the audit trail
  survives (step 8 builds on it).
- Use SQLAlchemy 2.0 (async, typed `Mapped[...]` models) with `asyncpg`, and **Alembic**
  for migrations. The first migration creates these tables. The app never calls
  `create_all`.
- Timestamps are timezone-aware UTC.

### 2. Key format and storage

- The format is `lgw_<key_id>_<secret>`:
  - `key_id`: 12 random characters, lowercase base32. It's public, and it's how we find
    the row in the database.
  - `secret`: 32 random bytes from `secrets.token_bytes`, URL-safe base64 without
    padding.
  - The `lgw_` prefix makes leaked keys easy to spot, for example with GitHub secret
    scanning.
- Store only `secret_hash = HMAC-SHA256(pepper, secret)`. The **pepper** is a server
  secret from the secret store (below), never kept in the database.
  - Explain in the ADR why a fast hash is right here and bcrypt/argon2 is not: those are
    built for low-entropy human passwords, while our keys have 256 bits of entropy, and
    a fast hash keeps per-request checks cheap. Also explain what the pepper adds (a
    leaked database alone can't verify anything).
- Verify with `hmac.compare_digest` (constant time). When the `key_id` is unknown, still
  do a dummy comparison, so response timing doesn't reveal which key IDs exist.
- The full key is shown **exactly once**, when it's created. It can't be recovered
  afterwards.

### 3. Authentication on requests

- `Authorization: Bearer lgw_...` is required on every `/v1/*` route. `/healthz` and the
  new `/readyz` stay public.
- Apply authentication as a **router-level dependency** for `/v1`, so a new endpoint
  can't forget it. A test must enumerate `app.routes` and prove every `/v1` route rejects
  a request with no key.
- Authentication runs **before the body is read**, so unauthenticated clients can't make
  us read a 2 MiB body.
- Every failure (missing header, malformed key, unknown, wrong secret, revoked, expired)
  returns the **same** 401: OpenAI envelope, type `invalid_request_error`, code
  `invalid_api_key`, and a generic message. The precise reason goes only into our logs.
  Never log the secret. Log the `key_id` only once the key is verified; log a
  malformed or unknown one as `null`.
- On success, attach a `Principal` (org id, team id, key id) to the request and
  `annotate()` all three, so every access-log line says who made the call. Steps 5 and 6
  will read this `Principal`.

### 4. Verified-key cache

- Checking the database on every request adds latency and load. Keep an in-process cache
  of **successful** verifications, keyed by `key_id` and storing the hash. Default TTL
  30 s, configurable, and bounded in size (LRU, default 10,000 entries). No new
  dependency: implement it in a small module with an injectable clock.
- Do **not** cache failures. Unknown keys must not be able to fill the cache. Brute-force
  protection is rate limiting, which is step 6; say so in the threat model.
- Consequence to document: **a revoked key keeps working for up to the TTL on each
  replica**. That's the trade-off for speed, and it goes in the ADR and the threat model.

### 5. Secret store

- A `SecretStore` protocol: `get(name: str) -> SecretStr | None`.
- Two implementations:
  - `env`: reads environment variables. This is the current behaviour, and existing
    `GATEWAY_PROVIDERS__*__API_KEY` configuration keeps working.
  - `file`: reads one file per secret from a directory, which is how Docker and
    Kubernetes secrets are mounted (e.g. `/run/secrets/<name>`). Strip one trailing
    newline. Refuse a directory or file readable by others (mode check) and say why in
    the error.
- Select it with `GATEWAY_SECRETS__BACKEND=env|file` and `GATEWAY_SECRETS__DIR` for
  `file`.
- Secrets to resolve: each provider's API key, the key-hashing pepper
  (`api_key_pepper`), and the database URL (it contains a password).
- A missing pepper or database URL fails at startup with a clear message. The pepper must
  be at least 32 bytes.
- Cloud backends (AWS Secrets Manager, Vault) are out of scope, but the protocol must
  make adding one a single new class.

### 6. Admin CLI (not an HTTP admin API)

Managing tenants happens through a command-line tool that talks to the database
directly, so no admin endpoint is exposed to the network. The HTTP admin API is step 12.

```bash
uv run gateway-admin create-org <name>
uv run gateway-admin create-team <org> <name>
uv run gateway-admin create-key <org> <team> <name> [--expires-in-days N]   # prints the key ONCE
uv run gateway-admin list-keys <org> [<team>]      # key_id, name, status; never secrets
uv run gateway-admin revoke-key <key_id>
```

- Use `argparse`, not a new dependency. Register it as a `[project.scripts]` entry point.
- Output is for humans, but `create-key` must print the full key alone on its own line,
  so it's easy to copy.

### 7. Readiness

- `/readyz` returns 200 only when the database answers a trivial query; otherwise 503 with
  the OpenAI error envelope. `/healthz` stays liveness-only (see architecture doc).

## Local development and CI

- Add `compose.yaml` with a Postgres 17 service for local development and tests. Pin the
  image version, and give it a healthcheck.
- Tests that need Postgres use the marker `db` and read `GATEWAY_TEST_DATABASE_URL`:
  - When it's set, they run. Apply the migrations to a fresh database/schema per test
    session, and isolate each test (a transaction rolled back, or truncation).
  - When it's unset locally, skip them with a visible reason.
  - When `CI=true` and it's unset or unreachable, **fail**. CI must never silently skip
    database tests.
- CI (`.github/workflows/ci.yml`): add a `postgres:17` service container, set the env
  var, and run the migrations as a step, so CI proves they apply cleanly.
- Update `AGENTS.md` "Commands" and "Definition of done" with the Postgres commands
  (`docker compose up -d`, the test command with the env var).
- API-level tests that don't test SQL itself may use an in-memory implementation of the
  key repository protocol, so the default suite stays fast. The Postgres repository must
  have its own `db` tests covering the same contract.

## Tests required

1. Every `/v1` route rejects: no header, a non-Bearer scheme, a malformed key, an unknown
   `key_id`, a wrong secret, a revoked key, and an expired key. Each returns the
   identical 401 body.
2. A valid key reaches the provider. The access log contains org, team and key IDs, and
   **no log line contains the secret** (search all captured logs).
3. The database never stores the plaintext secret (`db` test: create a key, then check
   the row contains no substring of the secret).
4. Cache: a revoked key is still accepted within the TTL and rejected after it (injected
   clock). Failures are not cached. The size bound evicts the least recently used entry.
5. Secret store: env and file backends; missing secrets; the file-permission refusal;
   the trailing-newline strip; and the startup failure when the pepper or database URL
   is missing or the pepper is too short.
6. The CLI end to end against Postgres (`db`): create org → team → key, use the key
   through the app, revoke it, confirm it's rejected after the TTL.
7. `/readyz`: 200 with the database up, and 503 when it's unreachable.
8. Migrations: upgrade from empty to head works (`db`). CI runs this too.
9. The live tests (`tests/live/`) keep working. Their fixture creates an in-memory
   tenant and key.

## Docs required

- **`docs/security/threat-model.md`**, in plain language. A table of: what could go
  wrong → how likely/bad → how we prevent it → what's left over. It must at least cover:
  a stolen client key, a database leak, a log leak, brute-forcing keys, finding out which
  key IDs exist, the revocation delay, a leaked provider key, misuse of the admin CLI, and
  a malicious base-URL override. Be honest about the gaps later steps close, like rate
  limiting in step 6 and the audit log in step 8.
- **ADR 0006:** key format, HMAC and pepper, and the cache trade-off.
- **ADR 0007:** the secret store abstraction, and the CLI-instead-of-API choice.
- **`docs/architecture.md`:** a "Step 4" section in plain language. Explain hashing vs
  encryption (why we never need to decrypt a key), what a pepper is, what a tenant is,
  what a migration is, and liveness vs readiness. Use analogies.
- **README:** a quickstart that now includes `docker compose up -d`, running the
  migrations, creating a key with the CLI, and using it with curl and the OpenAI SDK.
  Update `.env.example`. **`docs/roadmap.md`:** step 4 done, step 5 next.

## Allowed new dependencies

`sqlalchemy[asyncio]`, `asyncpg`, `alembic`. Nothing else without justification.

## Out of scope

Rate limiting and budgets, per-key model restrictions, the HTTP admin API, SSO/OAuth for
humans, automatic key rotation, cloud secret managers, usage/cost records.

## Report back with

- The final output of the four gates **and** the `db` test run (with Postgres running).
- The design as built, with a file list, and every open decision and what you chose.
- The threat-model table's rows, summarised in one line each.
- Tests changed or removed, and why.
- `git log --oneline main..HEAD`
