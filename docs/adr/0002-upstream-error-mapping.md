# ADR 0002: How provider errors are translated for clients

- **Status:** Accepted
- **Date:** 2026-09-25

## Context

A provider error can mean "the client's request is wrong", "our setup is wrong", or "the
provider is unhealthy". Forwarding the provider's status code as it is misleads clients and
can leak details about our provider account.

## Decision

| Provider result | Client gets | Code | Provider message passed on? |
|---|---|---|---|
| 400, 404, 413, 422, other 4xx | same status | `upstream_rejected_request` | Yes: the client needs it to fix the request |
| 401, 403 | **502** | `upstream_auth_failed` | No: it's our credential problem, logged at error level |
| 408 | 504 | `upstream_timeout` | No |
| 429 | 429 + `Retry-After` | `upstream_rate_limited` | Yes |
| 5xx | 502 | `upstream_server_error` | No |
| Can't connect | 502 | `upstream_unavailable` | n/a |
| Connect or read timeout | 504 | `upstream_timeout` | n/a |
| All pooled connections busy | 503 | `gateway_overloaded` | n/a |
| Failure after streaming began | the 200 already sent, then a final `data: {"error": ...}` event | same codes | n/a |

## Consequences

- A client never sees a 401 caused by our provider key, so it won't rotate its own key by
  mistake.
- 502, 503 and 504 clearly mean "not your fault, retry may help". Step 7 retries and fallback
  rely on the same distinction.
- Once a stream has started, the status code can't change. The error event is the only
  signal, and OpenAI SDKs raise an exception on it.
