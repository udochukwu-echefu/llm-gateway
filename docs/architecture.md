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

## What the gateway deliberately does NOT do yet

- **No authentication of clients.** Anyone who can reach it can use our key. Only run it
  on your own machine until step 4.
- One provider at a time (step 3 adds more, chosen per request).
- No limits, cost tracking, retries, or caching (steps 5–10).

See [roadmap.md](roadmap.md) for the order.
