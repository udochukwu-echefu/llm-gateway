# Architecture, in plain language

This document explains how the gateway works and why, assuming no prior knowledge of
gateways. It grows with each build step.

## What a gateway is

Picture a company with 20 internal apps that all want to use AI models. Without a gateway,
every app holds its own provider keys, handles provider outages its own way, and nobody
knows the total spend.

A gateway is **one front door** that every app goes through:

```
  App A ─┐                         ┌─> Groq
  App B ─┼──>  LLM GATEWAY  ───────┼─> Gemini
  App C ─┘                         └─> DeepSeek
```

Apps speak one language to the gateway. The gateway holds the provider keys, enforces
limits, counts cost, and switches providers when one is down. Apps don't need to know
any of that.

## The final picture (where we're going)

```
                    ┌────────────── Load balancer ──────────────┐
                    │                                            │
               Gateway copy 1                              Gateway copy 2 ... N
          (identical, stateless)                        (identical, stateless)
                    │                                            │
       ┌────────────┼──────────────┬─────────────────────┐      │
       ▼            ▼              ▼                     ▼      ▼
    Redis       Postgres     Secrets manager      Model providers
 (fast counters: (tenants, keys,  (provider API     (Groq, Gemini,
  rate limits,   budgets, usage   keys)              DeepSeek, OpenAI)
  short cache)   records)
```

- **Stateless** means a gateway copy remembers nothing between requests. Anything that
  must be remembered goes to Redis or Postgres. That lets us run 1 copy or 50, and the
  load balancer can send any request to any copy.
- **Redis** is an in-memory store: very fast, fine to lose a little. Good for "how many
  requests did team X send this minute?"
- **Postgres** is the durable database: slower, never loses data. Good for "who are our
  tenants?" and "what did team X spend in March?"
- **Secrets manager** is a locked box for the provider keys, so they never sit in code.

## Step 1: the pass-through proxy

Step 1 is a **pass-through proxy** to one provider:

```
 Client (any OpenAI SDK)
   │  POST /v1/chat/completions
   ▼
 ┌──────────────────────────── Gateway process ────────────────────────────┐
 │                                                                          │
 │  1. RequestContextMiddleware   (middleware.py)                           │
 │       gives the request an ID, times it, writes one log line at the end │
 │                          │                                               │
 │  2. chat_completions route     (routes.py)                               │
 │       checks: is it JSON? too big? has model + messages?                 │
 │                          │                                               │
 │  3. UpstreamClient             (upstream.py)                             │
 │       swaps in OUR provider key, sends it, translates provider errors   │
 │                          │                                               │
 └──────────────────────────┼───────────────────────────────────────────────┘
                            ▼
                    Provider (Groq by default)
```

### The files, one by one

| File | Job in one sentence |
|---|---|
| `config.py` | Reads settings from environment variables and refuses to start if one is missing or invalid. |
| `logging.py` | Makes every log line a JSON object, so machines can search them. |
| `middleware.py` | Wraps every request: assigns an ID, measures time, logs the outcome, catches crashes. |
| `routes.py` | The URL handlers: `/healthz` and `/v1/chat/completions`. |
| `upstream.py` | Talks to the provider and translates its errors into ours. |
| `errors.py` | One error shape (`{"error": {...}}`) for everything the gateway returns. |
| `main.py` | Wires it all together when the app starts. |

## Key ideas, explained

### Why copy OpenAI's API shape?
Almost every AI SDK and tool can already talk to "an OpenAI-compatible API". If the
gateway looks like OpenAI, a company's apps switch to it by changing one setting (the base
URL). No new SDK to learn. See [ADR 0001](adr/0001-openai-compatible-api.md).

### Streaming (SSE)
When ChatGPT types its answer word by word, that's streaming. The server keeps the
connection open and sends small pieces (**chunks**) as the model produces them, using a
format called **Server-Sent Events** (lines starting with `data: `).

The gateway passes each chunk on as soon as it arrives. It doesn't wait for the whole
answer. That's why the middleware is written as "plain ASGI" (the low-level Python web
server interface): some higher-level helpers quietly collect the whole response first,
which would break streaming.

### What if the user closes the tab mid-answer?
The model would keep generating and we'd keep paying for tokens nobody reads.
`UpstreamStreamingResponse` notices the client left and **closes the provider connection**
right away. A test proves it (`test_client_disconnect_mid_stream_releases_the_upstream_connection`).

### Connection pooling
Opening a secure connection (TCP + TLS handshake) costs roughly 50–150 ms. The gateway keeps
**one shared HTTP client** with a pool of open connections and reuses them, like keeping
the phone line open instead of redialing for every sentence.

### Timeouts: four kinds
| Timeout | Plain meaning | Default |
|---|---|---|
| connect | How long to wait to reach the provider at all | 5 s |
| write | How long to wait while sending our request | 10 s |
| read | Longest silence allowed between two chunks | 60 s |
| pool | How long to wait for a free connection when all are busy | 5 s |

Without timeouts, one stuck provider would eventually tie up every connection we have.

### Error translation (the subtle part)
The provider's errors don't always mean the same thing to our client. Example: if the
provider says **401 "invalid API key"**, that's *our* key that's wrong, not the client's.
Passing on a 401 would make the client think *their* key is bad. So we return **502**
("the gateway had a problem upstream") and log it loudly for us to fix.
The full table is in [ADR 0002](adr/0002-upstream-error-mapping.md).

### Request IDs
Every request gets a unique ID, returned in the `x-request-id` header and stamped on every
log line. When a customer says "request `3f9a…` failed", you can find exactly what happened.
We also log the **provider's** request ID, so you can quote it to Groq's support.

### Why we never log prompts
Prompts often contain personal or confidential data. Logs are copied to many places and
kept for a long time, so the gateway logs *about* the request (model, status, timing) but
never its content. A test enforces this.

### Validation: check at the door
Bad requests (not JSON, too large, missing `model`) are rejected **before** calling the
provider. That's faster for the client, costs us nothing, and shields the provider from junk.
The size limit is checked **while reading**, because a client can lie about the size in
its headers.

## Step 2: the gateway now understands what it carries

In step 1 the gateway was a **postman**: it passed envelopes along without opening them.
In step 2 it became a **translator's assistant**: it opens every letter, checks that it's
written correctly, and understands what's inside.

```
 Client JSON ──► schemas/chat.py checks it ──► to_upstream() builds the provider's body
                                                        │
 Client ◄── clean, checked chunks ◄── relay_chat_stream ◄── provider's stream
```

### New files

| File | Job in one sentence |
|---|---|
| `schemas/common.py` | The two base "rulebooks" (strict for requests, tolerant for responses) and `provider_options`. |
| `schemas/chat.py` | Exactly what a chat request, response and streamed chunk may contain. |
| `schemas/embeddings.py` | The same for embeddings (turning text into numbers for search and RAG). |
| `sse.py` | Reads the provider's stream and cuts it back into whole events. |
| `context.py` | Collects facts about a request (model, tokens) for its log line. |
| `api/chat.py`, `api/embeddings.py`, `api/health.py` | One file per endpoint group. |

### Key ideas, explained

**A schema is a contract.** It says "a chat request must have a `model` (text) and at
least one message; `temperature` is a number from 0 to 2". Pydantic turns that contract
into code that checks every request automatically.

**Strict in, tolerant out.** This follows an old rule: *be strict in what you send, and
forgiving in what you accept.* We control what clients may send us, so we're strict and
`temprature` (typo) gets a clear 400. We don't control providers, and they add new fields
all the time. If we were strict with them, our gateway would break every time Groq shipped
a feature. So for responses we only check the fields we actually use, and keep the rest.

**Discriminated unions.** A message can be a system, user, assistant or tool message, and
each has different rules. Instead of trying every rule and reporting four confusing
errors, the schema looks at one field (`role`) and picks the right rulebook. Same for
content parts (`type`: text, image, audio, file).

**`provider_options`.** Some features exist only on one provider. They go in a labelled box:

```json
{"model": "...", "messages": [...],
 "provider_options": {"groq": {"reasoning_format": "parsed"},
                      "deepseek": {"thinking": {"type": "enabled"}}}}
```

The gateway opens only the box of the provider that serves the request. That will matter
in step 7: if Groq is down and we fall back to DeepSeek, Groq's options won't confuse
DeepSeek. The box can't contain standard fields like `messages`. Otherwise someone could
hide messages there and get around guardrails we add in step 11.

**Why the stream is now parsed.** A streamed answer arrives as bytes cut at random places,
sometimes even in the middle of an emoji (one emoji = 4 bytes). `SSEDecoder` glues pieces
back into whole events before we read them. Then each event is checked like a mini
response. Parsing costs microseconds, while the model takes seconds.

**Usage and cost.** To know what a request cost, we need its token counts. Providers only
send them in a stream if you ask (`stream_options.include_usage`). So the gateway **always
asks**, records the numbers, and removes that extra chunk if the client didn't ask for it.
The client sees exactly what it expected, and we still get our numbers.

**Every stream ends clearly.** A stream now ends either with `[DONE]` or with an error
event. A provider that simply stops mid-answer is reported as
`upstream_stream_truncated`, so the client knows the answer is incomplete.

**Echoed history.** In a chat loop, apps send the model's last answer back as history.
That answer can contain output-only fields (`annotations`, DeepSeek's
`reasoning_content`). The assistant-message rulebook quietly drops those instead of
rejecting the request. It's the one deliberate exception to "strict in".

Full reasoning: [ADR 0003](adr/0003-canonical-schema.md).

## Step 3: adapters choose the provider for each request

An **adapter** is like a travel plug: the appliance keeps the same plug, while the adapter
fits the local socket. Apps keep sending the canonical OpenAI format. A small provider
adapter fits that request to Groq, DeepSeek, Gemini or OpenAI and translates the answer back.

```
Client: model="groq/openai/gpt-oss-120b"
  → API: validate request
  → registry: choose Groq, model="openai/gpt-oss-120b"
  → adapter: check capabilities, translate, call Groq
  → canonical answer/chunks (model="groq/<returned model>")
  → API: record usage, encode JSON or SSE for the client
```

The first slash selects the provider; later slashes belong to its model name. Unknown or
unconfigured providers return an actionable 404. Setting a provider's nested API key enables
it; at least one key is required at startup. Provider keys stay in `SecretStr`, a wrapper
that masks their printed representation.

**Capabilities** are the adapter's list of supported features. Checking them before making
a network call avoids paying network latency for a request we already know cannot work.
For example, Groq cannot serve embeddings. Where the meaning can be kept, we translate:
DeepSeek receives `max_tokens` instead of `max_completion_tokens`. Developer instructions
become system instructions for DeepSeek and Gemini. Undocumented parameters, including
Gemini token-limit options, pass through unchanged: missing documentation does not prove
non-support. Only explicit documented restrictions are rejected locally. Endpoint support
is not a promise that every model supports
every option; model-specific errors still come from the provider.

Each enabled provider has its own **connection pool**, a collection of reusable connections.
This is the **bulkhead pattern**, named after a ship's watertight compartments: flooding one
compartment does not flood the whole ship. A stalled provider can fill only its own pool.
The app creates those pools at startup and closes them on shutdown, including partial
startup failure. Global timeout and pool-size settings apply to each pool.

The adapter reads provider JSON/SSE and returns only canonical objects. The API no longer
sees provider response bytes. It still records token usage, hides unrequested usage, and
ends the client stream with `[DONE]` or an error. Closing the client connection closes the
provider stream under a cancellation shield: cleanup gets time to release the connection
even though the web server has cancelled the request.

`reasoning_content` is the optional separate reasoning text. DeepSeek already uses that
name; Groq's `reasoning` is translated. Ordinary content, including quoted `<think>` tags,
is not parsed as reasoning. Access logs contain provider, model, usage and provider
`x-request-id` when present (otherwise None), never prompts, answers or keys.

| File | Job |
|---|---|
| `providers/base.py` | Defines the adapter/stream contracts and frozen capability declaration. |
| `providers/registry.py` | Resolves provider-prefixed model names. |
| `providers/pools.py` | Owns provider HTTP-client lifetimes. |
| `providers/defaults.py` | Shares default URLs without importing adapters into configuration. |
| `providers/openai_compat.py` | Applies shared capability checks and canonical translations. |
| `providers/transport.py` | Performs HTTP I/O and ADR 0002 error mapping. |
| `providers/stream.py` | Decodes provider SSE into checked canonical chunks. |
| `providers/{groq,deepseek,gemini,openai}.py` | Declares verified provider differences and documentation sources. |
| `api/streaming.py` | Encodes client SSE, records/hides usage and closes provider streams. |

The old `upstream.py` is replaced. See [ADR 0004](adr/0004-provider-adapters.md) and
[ADR 0005](adr/0005-canonical-reasoning.md) for decisions and documentation gaps.

## Step 4: tenants, keys and secret storage

A **tenant** is an organization using the gateway. Inside it are teams; a team owns its
own client keys. Think of a shared office building: the organization rents the space,
teams have rooms, and each app gets its own access badge. Every `/v1/*` door checks
the badge before reading the request body. `/healthz` ("is the process alive?") stays
public; `/readyz` ("can it actually serve traffic?") asks Postgres to answer a simple
query. A live process can be unready when its database is down.

The badge is `lgw_<public ID>_<random secret>`. Postgres stores the ID and a **hash**,
not the secret. Hashing makes a one-way fingerprint: when the badge is presented we
make the fingerprint again and compare it. **Encryption** would require a key to
decrypt a stored secret, but the gateway never needs to show the badge again; keeping
decryptable copies would increase the damage from a leak. A **pepper** is a separate
server-only ingredient mixed into that fingerprint, like a private seasoning; it is
not stored in Postgres. `SecretStore` fetches it, provider keys and the database URL
from environment variables or permission-restricted mounted files.

The gateway keeps recently verified badges in a small cache to avoid a database query
every time. It rechecks the badge secret and expiry on each use; a revocation can take
up to the cache TTL (30 seconds by default) to take effect on each copy of the app.
Invalid badges are never cached. The `Principal` attached to an authenticated request
contains organization, team and key IDs, also recorded in access logs without secrets.

A **migration** is a versioned database change, like a step-by-step renovation plan.
Alembic creates the organizations, teams and key tables in the first migration; the
app does not silently invent tables at startup. `gateway-admin` creates and revokes
them directly in Postgres without opening a network admin route. See
[ADR 0006](adr/0006-virtual-api-keys.md), [ADR 0007](adr/0007-secret-store-and-cli.md)
and the [threat model](security/threat-model.md).

## Step 5: a price tag and a receipt for each provider call

The **model catalogue** (`catalog/models.toml`) is a reviewed list of models and
their USD prices. Think of a shop's approved price list: if an item isn't on it,
the gateway refuses the request before calling the provider. `/v1/models` shows
only items whose providers are configured. Editing the file needs code review;
the version is stamped onto each usage receipt so later price changes don't
rewrite yesterday's spend.
Gemini Embedding 2 has a published text-input rate; the gateway lists it for
text embeddings only. Images, audio and video have different prices, so those
cannot safely use the text price.
Google's embedding response currently omits token usage on its OpenAI-compatible
endpoint. These calls still succeed but their receipts have unknown cost rather
than an invented token estimate.
Each model may have several price periods. A request picks the rate effective
at its start time in UTC, even if its response finishes after midnight. Future
rates can be reviewed before they take effect without repricing old receipts.

Providers return token counts in different shapes. The adapters translate cache
hits into one `cached_tokens` field. Gemini sometimes reports fewer output tokens
than `total - prompt` because of hidden thinking; the adapter charges that
difference as output without pretending it knows the exact reasoning-token split.
Cost = uncached input tokens at the input
rate + cache hits at the cached rate (or input rate when there is no discount) +
output tokens at the output rate, divided by a million. Thinking/reasoning tokens
are included in output, not added again. Money uses **decimal arithmetic**:
binary floats cannot exactly represent most decimal fractions (for example,
`0.1 + 0.2 != 0.3` as floats), and tiny errors add up over millions of calls.
Postgres stores the exact decimal result in `NUMERIC`.

Writing a receipt directly to Postgres would hold up a customer's response.
Usage has its own plain-ASGI middleware (a thin wrapper around HTTP messages):
it observes the response and files the receipt when the call ends. The separate
request-context middleware only assigns IDs and writes access logs, so accounting
does not mix with request logging or buffer a streamed answer.
Instead a **background worker** writes them later, like a cashier putting receipts
into a tray while another person files them. The tray is a **bounded queue**: it
has a fixed capacity so an outage cannot fill all memory. The worker files a
**batch** (several receipts in one database transaction), reducing database
round-trips. If the tray fills, the record is dropped and logged, not the user's
response. Shutdown drains what it can, but a process killed without warning
loses receipts still in memory. This is not a durable invoice ledger.
The first queue drop logs immediately; later drops are grouped into at most
one summary per second when another drop occurs, rather than flooding logs
while the queue is full. The shutdown log still reports the total lost.

Each provider-bound call has one metadata-only record: tenant IDs, model, tokens,
cost, outcome and timing, never prompts or vectors. Even provider error statuses
get a zero-cost `not_billed` record. If a connection was refused, timed out
during connection, or no pool slot was available, the provider never received
the request: these also get `not_billed` with zero cost. Once a request might
have reached the provider, a read timeout has unknown cost (`usage_missing`).
A client may disconnect mid-stream before
the usage chunk arrives. The provider **probably still billed us**, but we have
no final token count: `stream_incomplete` stores a NULL cost. This is a known
accounting gap, not free usage. A stream error without usage is similarly visible
as `usage_missing`. `gateway-admin usage` aggregates costs and missing counts
in SQL so NULL costs aren't hidden in the sum. See [ADR 0008](adr/0008-reviewed-model-catalogue.md)
and [ADR 0009](adr/0009-batched-usage-writer.md).

## Step 6: limits as a shared turnstile

Redis is the shared turnstile for all gateway copies: each team has optional requests
per minute, recorded tokens per minute, simultaneous requests, and monthly USD spend
limits. A zero or unset default means **unlimited**. Team overrides live next to the
key's team in Postgres and arrive in the same database lookup as the badge; changes
become visible within the verified-key cache's TTL (30 seconds by default).

**Why a Lua script?** Imagine two librarians each see nine tickets used out of ten.
If they separately read and then write the tally, both admit a tenth visitor: eleven
get in. A Redis Lua script checks and updates without letting the other librarian
interleave, so exactly one gets the final ticket.

**Sliding window:** At 12:01:30, the last 60 seconds cover half of 12:00 and half of
12:01. If 12:00 had ten requests and 12:01 has two, the estimate is
`10 × 0.5 + 2 = 7`. A fixed window would forget the ten at 12:01:00 and invite a
boundary burst; a token bucket instead refills continuously. RPM adds a ticket when
admitted. TPM checks previously recorded tokens and adds actual input plus output
after the call, because the answer length is unknown ahead of time. In-flight calls
can overshoot TPM; the number of such calls is bounded by the team's concurrency limit
when one is configured (unlimited concurrency does not bound it).

A concurrency **lease** is like a library book with a due date: it is checked out
until the entire response ends, even if the client disconnects. If a gateway dies,
the due date eventually frees its slot. Merely counting active calls with increment
and decrement could leave a slot occupied forever after a crash. While a request is
still alive it renews the due date, so even long streams keep their slot; if the
gateway dies, no one renews it and the book becomes available again. Configure a
lease TTL longer than the longest period an active gateway might be unable to renew.

Budgets count exact integer pico-dollars (a trillionth of a USD) in Redis. Postgres
receipts rebuild a missing month counter, and one warning per month is logged when the
configured threshold is crossed. It is a **guard rail**, not a bank balance: unfinished
calls and calls without token usage have unknown costs, and queued receipts may not
yet be durable. Fail **open** means Redis trouble permits traffic (availability wins);
fail **closed** means 503 until Redis recovers (cost control wins). Redis errors are
logged without flooding. `/readyz` checks Redis but reports ready during an outage
in open mode.
The first request after a lost budget key can briefly wait for a Postgres rebuild.
That rebuild has one deadline (200 ms by default, including any lock wait); a timeout
uses the same open/closed policy rather than holding up the request indefinitely.
If Redis goes away without losing a month's key, fail-open calls may still leave its
spend tally too low. A background cashier compares Postgres receipts plus locally
queued receipts with Redis every five minutes and raises the tally when needed. The
cashier never lowers it while another gateway may still be adding costs. Persisted
budget drift heals by the next reconciliation; receipts that are permanently lost
cannot be recovered from Postgres.

Failed badge checks are also counted by socket IP *before* database lookup. An
untrusted `X-Forwarded-For` is just client-supplied text; if we believed it, an attacker
could choose a fresh IP on each try. Only explicitly configured trusted proxy hops
allow it to override the socket address. Valid badges do not reset bad-guess counts.

See [ADR 0010](adr/0010-redis-limits.md) and [ADR 0011](adr/0011-budgets-and-failure.md).

## Step 7: recover carefully when a provider fails

A **retry** asks the same provider again. That is safe when a connection never reached
it, but a lost answer might already have been generated and billed. We retry only the
agreed connection failures and selected overload/server statuses, up to twice. Read
timeouts do not retry unless an operator explicitly enables them. Even a server error
cannot guarantee a free repeat; compare receipts with provider invoices.

Imagine a crowd rushing a door just as it reopens. If everyone retries after exactly
one second, the provider gets knocked over again: the **thundering herd**. **Full jitter**
means each caller waits a different random time, from zero to a growing maximum
(default 0.25 seconds, then 0.5, capped at 2). Retry-After supplies the provider's own
wait instead; waits above the cap move straight to the next approved alternative.
A **retry budget** permits only one retry for every five first attempts in the last
minute. Otherwise a small outage could triple the traffic and overwhelm the surviving
capacity. Step 8 adds a minimum allowance of ten retries per provider per window. One 60-second stopwatch covers
all attempts and waits; each attempt gets only the time remaining. For streaming, this
stopwatch stops at the first chunk, while the normal silence timeout remains.

A **circuit breaker** is a fuse box for each provider. After at least ten attempts in
30 seconds, if half have failed, the fuse opens and stops sending traffic for 30 seconds.
Then it lets exactly one probe through: the **half-open** state. A good response closes
the fuse; another failure opens it again. Concurrent requests cannot all become probes.
Every gateway replica has its own fuse box in memory. They learn independently, which
may allow one probe per replica, but they still work when Redis is unavailable.

**Fallback** is like a substitute teacher: the approved substitute can keep the class
going, but may teach differently, and the class should be told. Here it also means
sending the user's prompt to a different company. The reviewed catalogue explicitly
lists approved alternatives in order. An empty list means no substitute. The gateway
skips an unavailable provider or one that cannot teach this lesson—for example, a
DeepSeek target cannot serve a json_schema request. Only the chosen provider's options
are sent. Alternatives have the same kind (chat or embeddings), exist in the catalogue,
and cannot refer to themselves or form a loop. Only the original model's direct list
is used; a substitute cannot nominate an unapproved substitute of its own.

Clients can say `x-lgw-fallback: disabled`. The returned `model` names the actual model.
If retries or fallback occurred, `x-lgw-attempts` counts network attempts and
`x-lgw-fallback-from` identifies the requested model. An open fuse with no usable
substitute returns `503 provider_unavailable`. Client errors never trigger fallback.
Once a provider stream opens, errors end that stream; they cannot restart an answer.

Accounting now writes one receipt per attempt, with an `attempt` number and optional
`fallback_from`, all sharing the client request ID. A failure does not disappear when
a later attempt succeeds. Redis adds all known token counts and costs, while the one
concurrency lease covers the entire client request. Failed calls can still have unknown
costs; the best-effort writer has not become an invoice ledger.

| File | Job |
|---|---|
| `resilience/service.py` | Executes retries and approved targets for both endpoints. |
| `resilience/retry.py` | Classifies failures, computes delays and reserves retry credit. |
| `resilience/breaker.py` | Owns each provider's local fuse and exclusive probe. |
| `resilience/fallback.py` | Resolves a catalogue target and reuses capability validation. |
| `resilience/attempt.py` | Binds one receipt to one network operation. |
| `resilience/stream.py` | Enforces first-chunk deadline and observes streaming outcomes. |
| `usage/finalization.py` | Settles every receipt and releases the single lease. |

See [ADR 0012](adr/0012-safe-retries.md) and
[ADR 0013](adr/0013-breakers-and-approved-fallbacks.md).

## Step 8: see the service and account for administrative changes

**Metrics, logs and traces** answer different questions. Metrics are a car's dashboard:
traffic, errors, speed and fuel consumption at a glance. Logs are its trip diary: individual
metadata entries explaining events. A trace is the GPS track of one journey: a server
request contains authentication, admission checks, each provider attempt and usage enqueue.
A trace ID joins that journey to JSON logs from the gateway, uvicorn and other libraries.
No prompts, answers, vectors, credentials or exception messages go into traces.

**Cardinality** is the number of different labelled series. A counter for four providers
is small; a counter for millions of request IDs is not. Metrics use only fixed routes,
configured providers, reviewed catalogue models and bounded outcomes/reasons. Unknown paths
become `other`. They never use team, key, user, request or IP labels. Per-team reporting
stays in Postgres. Each app owns an injected registry, so tests and app instances cannot
share accidental global counters. The metrics socket defaults to `127.0.0.1:9464`, separate
from the customer API; traffic and spend should not be public.

A **percentile** describes the slow tail. p99 is the duration below which 99 of 100 requests
finish. An average can look healthy while one customer in a hundred waits much longer.
The dashboard shows p50 and p99. Gateway overhead subtracts time awaiting providers from
elapsed request time; for streams both measurements stop at the first nonempty body byte.
Provider reads are timed while awaiting each chunk, excluding client backpressure between
chunks. Retries contribute all their provider waits; backoff remains gateway overhead.
The target is overhead below 10 ms at p99: the gateway controls its own delay, not how fast
a model generates an answer. This implementation measures overhead; it does not claim the
step 12 load-test target has already been proven.

Token and cost counters record known per-attempt usage, even when the receipt queue drops a
record. Cached tokens are a subset of input and reasoning tokens a subset of output; don't
add those subsets twice. `cost_usd_total` is a monitoring trend, **not the accounting record**;
Postgres is the accounting record, with the best-effort limitations explained in step 5.
Queue depth, drops and losses make missing receipts visible. Circuit states are 0 closed,
1 half-open and 2 open. Prometheus alert rules flag persistent circuits, error rates,
overhead, receipt losses and rising Redis errors. Delivery to a paging service is deferred.

Tracing uses manual spans and an application-owned OpenTelemetry provider. Without an OTLP
endpoint there is no exporter or exporter thread. Incoming W3C `traceparent` is accepted;
external providers do not receive trace context unless an operator explicitly opts in.
The local profile runs a provisioned Grafana dashboard, Prometheus and Jaeger. The container's
metrics socket binds internally to all interfaces so Prometheus can scrape it, but it has
no published host port. All published local UI and API ports bind to loopback.

**The audit hash chain** is a numbered notebook where every page includes a fingerprint of
the previous page. Editing an old page changes its fingerprint and breaks the next link.
Each event hashes its previous hash plus canonical JSON: sorted keys, compact UTF-8, UTC
microsecond timestamps, and no floating-point amounts. An advisory lock is the notebook's
single pen: one transaction owns it until commit or rollback, so concurrent operators
cannot write two different next pages. Sequence IDs can have gaps after rolled-back writes;
verification follows the hash links, not consecutive numbers.

Every admin change and its event commit together. A database trigger rejects updates and
deletes; verification reports the first broken link. Details are an allowlist of numeric
limit/budget changes, never arbitrary command arguments, names, keys, hashes or URLs.
The actor comes from `GATEWAY_ADMIN_ACTOR`, or OS username and hostname. It identifies an
operator's claim, not an authenticated person. A database owner can disable the trigger and
rewrite the whole chain or remove its tail; detecting that requires an externally retained
trusted hash/checkpoint. This is tamper evidence, not protection against the database owner.

The retry budget now has a minimum allowance of ten retries per provider per rolling minute,
or 20% of first attempts when that is larger. The amounts are not added. This lets low-traffic
requests recover without removing the proportional protection at higher traffic. Cancellation
is recorded as `client_disconnected`; unexpected attempt failures as `gateway_error`, and
both abandon an exclusive half-open probe safely. See ADRs 0012, 0014 and 0015.

## Step 9: tickets, stable names and controlled trials

A model policy is a list of destinations a team may visit. The organization sets the outer
boundary; a team's list can only make it smaller. This is an **intersection**: a destination
must appear in both lists when both exist. No organization policy allows the whole reviewed
catalogue, and no team policy inherits the organization policy. Patterns name one model or
all models at one provider, such as `groq/*`.

Checking a passenger's ticket at the booking desk is not enough if someone changes their
flight afterward. Check it at the gate, where the actual destination is known. The gateway
resolves an alias before authorizing the concrete model, and checks every possible fallback
again. If Groq is down but the team cannot use DeepSeek, the request fails safely instead of
sending the prompt to DeepSeek. Forbidden destinations never reach the provider. These checks
run before budget and rate admission, so denied requests do not spend RPM or reserve a lease.

An **alias** is a stable nickname like `fast`, `smart` or `embed`. Apps keep their nickname
while the platform team reviews changes to its destinations in the catalogue. A name without
a slash is an alias; `provider/model` always names a concrete model. The answer still names
the actual provider/model, and `x-lgw-alias` records which nickname the client used.

A **weighted trial** sends a proportion of requests to a candidate. With weights 90 and 10,
each request independently has a 90% chance of choosing the first model and a 10% chance of
choosing the second. Ten requests need not split nine and one. Forbidden targets are removed
first, and the remaining weights are rescaled. Unconfigured or not-yet-priced targets are
also removed. Retries keep the choice; fallback can only use separately approved, permitted
destinations. Every attempt's receipt keeps the alias so SQL can compare trial cost and
latency. The bounded alias label on the upstream request counter supports Grafana comparisons.

`gateway-admin set-models`, `clear-models` and `show-models` manage the policies offline.
Changes and their audit entries commit together. The key lookup reads both lists and caches
them with the verified identity: a change takes effect within the original cache TTL, normally
30 seconds, even under continuous use. `/v1/models` shows each team only its usable concrete
models and aliases. The CLI reports catalogue permissions; runtime availability also depends
on configured providers and active prices. See ADRs 0016 and 0017.

## Step 10: a sealed photocopy of an answer

A cache is a photocopy of an answer we already paid for. If the same team asks for the
same embedding again, the gateway can hand back that copy without paying the provider.
Chat needs an explicit opt-in: a model may intentionally answer the same prompt differently.
The gateway checks the badge, resolves the real model behind an alias, checks permission
and counts the request toward RPM before looking for a copy. A hit costs no model tokens,
spend or concurrency slot. The price-list version is part of the lookup address, so a
reviewed model change cannot silently reuse yesterday's copy.

An HR team and an engineering team must not see each other's answers, even inside one
company. Each lookup includes the team ID. The prompt itself is never in the address;
its contents are fingerprinted (hashed). Redis may copy its contents to disk, so answers
are encrypted. The sealed ciphertext is also *bound* to its lookup address, like a sealed
envelope addressed to one person: copying it to another team's address will not open it.

**Single-flight** means ten simultaneous identical requests on one gateway copy follow
one leader and share its completed answer, instead of making ten paid calls. If the leader
fails, followers can call the provider themselves. Streams are not cached: a partial
answer cannot safely be replayed as a complete one. The offline purge command removes
one team's or all of an organization's cached copies; every purge has an audit entry.
See ADRs 0018 and 0019.

## Step 11: replace names with codes before passing notes

Imagine a translator who swaps names for codes before passing notes to a stranger, then
swaps the codes back when the reply returns. Here `ada@example.com` becomes `[EMAIL_1]`.
Repeating the same email repeats the same code, so the model can follow references. The
translator's notebook stays only in this request's memory: it never goes into logs,
traces, Postgres or Redis. A cached reply still contains codes, and each new caller gets
their own fresh translation back. Literal codes already in a prompt are reserved to avoid
accidentally treating them as newly redacted values.

**Guardrails** are deterministic checks before data leaves the gateway. API/private keys
are blocked by default, payment cards and IBANs are redacted, and other recognized personal
data (emails, phones and IP addresses) are allowed unless an organization or team tightens
the policy. An action can allow, redact or block. The strictest of defaults, organization
and team wins; a team cannot weaken its organization. A rejected prompt consumes no RPM,
provider call or usage receipt. Offline CLI changes and their audit events commit together
and become effective within the existing key-cache TTL.

**Checksums** are arithmetic consistency checks. Luhn checks card digits; mod-97 checks
IBAN digits and letters. Most random order numbers fail them, cutting false positives.
They do not prove that an account exists.
Card checks use whole digit groups, so a separated CVV or expiry does not hide the card.
Only reviewed card layouts are accepted; overlapping valid candidates are masked together
so choosing one cannot leave another candidate's digits exposed.
Large inspections (32 Ki characters in total) run in a worker thread, letting the event
loop answer other requests such as health checks while the scan works. Threads still
share Python's interpreter lock, so this is responsiveness protection, not CPU isolation;
step 12 will load-test contention. Card checking keeps only five groups at a time and
reuses checksum arithmetic instead of repeatedly examining the same digits.
They do not search substrings of long unseparated numbers, which would often mistake
tracking numbers for cards.
Phone matching excludes date/time shapes and requires a plus prefix, 10–15 digits,
or recognizable local phone grouping, so a plain seven-digit count is left intact.
**Pattern matching** cannot catch everything:
names, addresses, obfuscated emails, unknown key formats and encoded data can escape it.
Images, audio, files and integer embedding-token inputs are not inspected. Presidio, a
context-aware personal-data recognizer, is one possible future extension.

Streaming can split a code into `[EMA`, `IL_`, `1]`. A small buffer holds only a possible
unfinished code; unrelated text goes straight through. Each choice, reasoning field,
refusal and tool argument has its own buffer. New nonstreaming output is inspected before
restoring known input codes, so new sensitive data can be masked or blocked without
masking the originals the caller already supplied. Streams only **detect** new output
findings at the end: bytes already sent cannot be taken back. That detection uses a
request-local copy of generated text, separate from the small delivery buffer.

**Data residency** means restrictions on where data is processed or stored. Laws and
contracts may restrict transfers across borders, but a region label is not a complete
legal assessment. The reviewed catalogue uses official processing/privacy documentation;
a US storage promise alone is not a US inference promise. Unknown locations stay `unknown`,
and global endpoints stay `global`. Organization and team allowed regions intersect inside
the same policy engine that already checks model access. It filters concrete destinations
behind aliases, weighted trials and fallbacks, and hides denied destinations in `/v1/models`.
An EU-only policy currently permits none of the reviewed models; we do not invent an EU
guarantee to make the list look more useful.

Visibility consists of detector counts: `lgw_guardrail_findings_total`, one final
`guardrail_findings` log event, `guardrails.input` / `guardrails.output` spans and nullable
`redaction_count` in each receipt. Values and restore mappings never enter them. See
[ADR 0020](adr/0020-deterministic-guardrails.md) and
[ADR 0021](adr/0021-redaction-restore-and-residency.md) for limits and verified sources.

## Step 12a: a private management door and a usage view

Applications still use the public `/v1` door with a team key. Administrators use a
different door: a loopback HTTP listener on port 8081 with `lgwa_` admin keys. The
admin door can be enabled for an internal portal, while the public port has no admin
routes. Its first platform key comes from the database-connected CLI, so a fresh
deployment cannot grant itself admin access over HTTP.

An **IDOR** bug means someone changes an ID in a URL and sees another tenant's data.
For example, an org administrator might replace their organization's name in
`/admin/v1/orgs/acme/teams` with a competitor's name. The service checks every
resource against the verified admin key's organization UUID before reading or
changing it. It responds with 404 for a different organization, revealing no more
than it does for a nonexistent one. A test matrix lists every admin route and tests
platform, own-org, other-org and missing-key access; adding a route without a matrix
row fails the inventory test.

The CLI and HTTP handlers call the same admin service. A changed setting and its
audit event commit together. HTTP events name the verified admin key ID as their
actor. If an admin tool retries a create request after losing its response, an
`Idempotency-Key` repeats the same creation metadata for 24 hours rather than creating
a second team or key. A client key is shown only in the first response. A retry returns
its key ID without the secret; if the first response was lost, the tool revokes that
key and creates a new one. Postgres never holds a usable client key, even encrypted.
Admins can read team limits and budgets and the org or team model, guardrail and
residency policies over the private door. Each read shows what was saved and what is
currently effective after defaults and inherited org rules, so a management tool can
display why a team has a particular setting.

Per-team spend would make too many Prometheus label combinations, so the usage
dashboard queries Postgres. Its database login has read permission only for
organizations, teams, usage receipts and a budget-only view. It cannot see key hashes or change
records. The dashboard shows spend against budget, models, traffic, cache savings
and unknown-cost calls; unknown cost is visible rather than mistaken for zero.
See [ADR 0022](adr/0022-admin-api.md).

## Step 12b: measure the gateway rather than the model

A **load test** sends requests at a declared rate and records how the gateway behaves
as that rate increases. An **open-loop** generator keeps sending that offered rate even
if responses slow down; otherwise slower responses could quietly reduce the pressure.
A **soak test** holds a steady load for ten minutes, looking for rising memory, receipt
loss and queues that cannot drain. It is a useful observation, not proof that no leak
can ever happen.

The fake provider is a metronome: it waits 200 ms, returns synthetic text or vectors
and known token counts, and emits 20 streaming chunks at 50 ms intervals. We measure
it directly first so it cannot hide as the bottleneck. There are no real-provider costs
or unpredictable model answers. The load-test replicas have only an internal Docker
network and point exclusively at that fake server. The runner ignores the owner's
`.env`; generated credentials and CLI-issued keys stay in private ignored files.

**p99** is the slow tail, below which 99% of requests fall. An average can look fine
while one caller in a hundred waits too long. We subtract awaited provider operations
using the existing overhead metric; for streams it stops at the first body byte. We
add histogram buckets across replicas before estimating p99, rather than averaging
their p99s. Bucket interpolation is approximate: the first campaign
used a coarse 10–25 ms bucket. The amendment adds finer boundaries and exact
per-request overhead logs for benchmark verdicts. Short prompts still run guardrails; S4 measures additional work
for a 5 KB PII-rich prompt without pretending the existing metric subtracts scans.

A **scaling factor** is two-replica saturation throughput divided by one-replica
saturation throughput, using the highest tested stage with fewer than 0.1% errors.
Two means doubling measured throughput; below two suggests a shared bottleneck or
coordination cost. This is independent of whether an overhead SLO capacity exists.

A **flame graph** stacks sampled function calls. Wider boxes appear in more samples;
the vertical axis is call depth, not elapsed time. It guides investigation, not proof
that every wide function can safely be optimized. We publish only stack samples, never
locals, prompts or credentials. No product optimization is included in this step.

Fresh teams isolate counters and accounting for every run. k6 validates complete
responses and terminal streaming events, separately counts expected RPM rejections,
and treats missed scheduled iterations as generator insufficiency. The soak compares
durable usage records against successful provider calls after the writer flushes.
All repetitions remain available; the report names each selected run.
See [reproduction commands](../loadtest/README.md),
[ADR 0023](adr/0023-controlled-load-testing.md), and the
[benchmark report](benchmarks/load-test-report.md) for measurements and limitations.

## What the gateway deliberately does NOT do yet

- No semantic, streaming or cross-team response cache.
- No admin SSO, admin web UI or automated key rotation.

See [roadmap.md](roadmap.md) for the order.

## Step 12b amendment: request slots shared by replicas

GCRA (Generic Cell Rate Algorithm) gives each request the next free time slot.
Slots are spaced 60 / RPM seconds apart. The gateway admits a request only if
its slot is not too far in the future. B is the immediate burst allowance,
normally 5% of RPM rounded up, at least one. A shared Redis clock and atomic
Lua decision keep replicas consistent. Any rolling minute admits at most RPM + B
while Redis is available and retains state. Retry headers describe when the next
slot becomes usable. Token limits remain approximate: actual tokens are only
known after a response, and their weighted minute counter can overshoot.

Exact overhead_ms in each access log uses the same unrounded observation as the
histogram, including provider-wait subtraction and the first-body-byte boundary
for streams. Observability finalizes once through a request-scoped callback before
the access line is written, while the request trace remains active. key_cache identifies a hit or database lookup (miss);
requests without a parsed key have null. Labels remain unchanged. Finer histogram
buckets near 10 ms reduce interpolation error; benchmark verdicts use the actual
request values, not interpolated bucket estimates.

The amended campaign starts every run with 30 seconds of excluded warmup. The
10–800 requests/s ramps measure at least 3000 requests per stage and continue
after overhead misses, stopping at >1% errors, client p99 above five times the
fake-provider baseline, or incomplete telemetry. Dropped iterations are retained without stopping
the ramp on their own. SLO capacity uses
exact p99 <10 ms and errors <0.1%; saturation throughput uses errors <0.1%.
Streaming, PII and the ten-minute soak always run at half the selected SLO
capacity, or 50/s if there is none. The 1/s five-minute idle path separates
verified-key cache hits and misses and has no SLO verdict. S1/S3/S6 repeat three
times; S2/S4/idle/S7 once, while S5 retains three repetitions.

The amendment defines saturation eligibility only by HTTP errors. A generator can
miss scheduled requests while the ones it sent mostly succeed. We therefore show
both actual successful responses per second under that definition and the highest
eligible stage where every scheduled request was sent. The latter gives stronger
capacity evidence. Generation coverage is also reported beside SLO capacity.
