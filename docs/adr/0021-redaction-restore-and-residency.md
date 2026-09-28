# ADR 0021: Request-local restore and conservative data residency

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Removing personal data entirely can make a task useless. Typed codes preserve references
while keeping originals away from providers. Region restrictions must apply to actual
destinations, including outage recovery, rather than client-visible nicknames.

## Decision

Replace identical type/value pairs consistently within a request (`[EMAIL_1]`, etc.).
Reserve placeholder-like literals already in the input before assigning codes, avoiding
collisions with user-provided codes. The reverse mapping belongs only to the request
session, is never attached to a receipt/cache/trace, and is cleared at finalization.
Restoration is a single non-recursive substitution: an original containing another code
does not recursively disclose another value. This cannot guarantee that a model will
repeat a code correctly or prevent it guessing a code for another value in the same request.

Cache fingerprints use the redacted request, and values are output-checked but not restored.
Each hit uses the current request's mapping. Consequently two different originals with
the same redacted structure intentionally share a team cache entry. Output is scanned
again on hits under the current effective policy. No cached entry contains restored input
originals. Existing unredacted entries are separated by the catalogue version bump.

Scan newly generated nonstreaming text **before** restoring known input codes; otherwise
restored cards would immediately be masked again, defeating restore. This interprets
“output restore + output scan” as two output stages, distinguishing known input values
from newly generated PII. New output redactions use a separate `[OUTPUT_CARD_NUMBER_1]`
namespace with no restoration. Output blocks are `502 guardrail_blocked_output`; the
provider attempt still has its actual token/cost receipt, marked upstream error.

For streams, a hold-back buffer per choice/text field/tool argument channel retains only
a suffix that is a proper prefix of an actual request placeholder. Its length is strictly
less than the longest assigned placeholder. Two- and three-chunk splits therefore restore
without holding unrelated text. Flush incomplete suffixes at finish/DONE; closing a stream
still closes its provider under the existing cancellation shield.

Stream output scanning is detect-only: already emitted bytes cannot be retracted. Scan
the pre-restore text assembled independently per channel at completion/close, including
partial output on disconnect, then release it. This detection copy is sensitive,
request-local memory proportional to generated text; it adds no disk persistence or
delivery hold-back but is not a bounded-memory output scanner. Incremental stateful
detectors are a future improvement for very long streams. Only counts go to final logs
and metrics. Detection actions retain their policy labels even though streams only detect.

Residency lives inside `ModelPolicy`: a concrete model must satisfy both pattern policies
and both allowed-region lists. NULL means all regions, intersection may be empty, and
`global`/`unknown` are literal categories, never wildcards for `us` or `eu`. The same check
filters weighted targets, aliases, fallback targets and `/v1/models`. Direct region denial
returns `403 model_not_allowed` naming the region. Disallowed fallback targets are skipped
per ADR 0016: an exhausted provider retains its error, or an open primary returns 503.

Catalogue entries carry `region`, `region_source_url` and `region_checked_on`. A missing
region defaults conservatively to `unknown` for older/custom catalogues; the reviewed
catalogue explicitly supplies all three fields. Official sources checked **2026-09-27**:

| Catalogue model | Region | Official source and interpretation |
|---|---|---|
| `groq/openai/gpt-oss-20b` | `unknown` | [Groq data controls](https://console.groq.com/docs/your-data): US GCP **retention** does not promise a US-only inference location. |
| `groq/openai/gpt-oss-120b` | `unknown` | [Same Groq terms](https://console.groq.com/docs/your-data), same public endpoint and limitation. |
| `deepseek/deepseek-flash` | `cn` | [DeepSeek privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html), “Where We Store Your Personal Data”: directly collect, **process and store** in PRC. |
| `gemini/gemini-3.8-flash` | `global` | [Gemini API terms](https://ai.google.dev/gemini-api/terms): data may be transiently stored/cached in any country with Google/agent facilities; no regional processing guarantee. |
| `gemini/gemini-embedding-2` | `global` | [Same Gemini API terms](https://ai.google.dev/gemini-api/terms); Developer API, not regional Vertex infrastructure. |
| `openai/gpt-4.1-nano` | `global` | [OpenAI data controls](https://platform.openai.com/docs/guides/your-data): default global endpoint has no processing constraint; regional eligibility/configuration cannot be assumed. |
| `openai/text-embedding-3-small` | `global` | [Same OpenAI data controls](https://platform.openai.com/docs/guides/your-data); model eligibility is not enabled residency. |

## Consequences

Residency is a routing control, not legal certification. Storage and inference processing
are different promises. DeepSeek's policy also says downstream application developers
must publish their own end-user policies; its PRC processing statement does not discharge
those responsibilities. Contracts, subprocessors, transfers, account settings and actual
deployment endpoints still need review. Changing a provider base URL requires re-reviewing
the catalogue region; a privileged operator can invalidate any declaration. No live test
can prove the physical location of inference from an API response.

Python does not promise secure erasure of strings from process memory. Crash dumps,
debuggers and process compromise can expose mappings; restrict these operationally.
Neither placeholders nor pseudonymisation guarantee anonymity: surrounding context may
identify people. The deterministic token numbering is binding and intentionally retained.

## Alternatives considered

- Persist restore mappings in Redis: rejected; extends sensitive-data lifetime and scope.
- Restore before caching: would return another request's original values on a hit.
- Scan restored input values as new output: contradicts useful restoration.
- Buffer the entire stream before delivery: loses streaming and still changes its contract.
- Infer region from company headquarters or storage-only claims: rejected; never guess.
