# ADR 0020: Deterministic guardrails before admission

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

The gateway is the last inspection point before a third party receives a prompt.
Inspection must have predictable behaviour, no external service and no new dependency.
Tenant controls must not let a team weaken its organization's protections.

## Decision

Use a pure scanner returning character spans and detector names, never logging matches.
Compiled patterns recognize API keys (including gateway keys), complete private-key
blocks, emails with a TLD, 7–15-digit phones, cards with Luhn validation, IBANs with
mod-97 validation, and IPv4/IPv6 parsed with Python's `ipaddress` module. Card candidates
have 13–19 digits. These are format checks, not verification of an actual account.

Review amendment: for space/tab/dash-separated number runs, examine whole-group windows
only in layouts **4-4-4-4, 4-6-5, 4-6-4, 4-4-4-4-3**, or a single 13–19-digit group.
Source checked 2026-09-28: [Baymard's card spacing reference](https://baymard.com/checkout-usability/credit-card-patterns)
lists these respectively for Visa/Mastercard, Amex, Diners Club, and 19-digit Maestro.
This is the reviewed subset, not a claim that every card format is supported. Luhn is
still required. Merge overlapping valid windows into their **union**: preferring only
one window can leave a real card's leading digits exposed when a CVV/expiry accidentally
forms a longer valid number. Over-redaction of ambiguous neighbours is the safe choice.
Do not slide inside an unseparated group longer than 19 digits: arbitrary 16-digit
windows pass Luhn about 10% of the time. A card concatenated directly with other digits
without separators remains a deliberate residual gap to avoid flagging tracking numbers.

Phone review amendment: retain the 7–15-digit bound, but require a leading `+`, at
least 10 digits, or local phone-style grouping (`3-4` or `2/3-3-2/3` digit groups,
separated by spaces/dashes). Exclude candidates overlapping date/time shapes
`YYYY-MM-DD`, `DD/MM/YYYY` and `HH:MM`, including impossible calendar values: shape,
not calendar validity, is the exclusion. Plain 7–9-digit counts are not phones.
Plain 10–15-digit counts can still be false positives under this explicit heuristic;
phone-style formatting is evidence, not proof that a number belongs to a telephone.

ReDoS means regular-expression denial of service: an attacker supplies text that makes
an engine try exponentially many ways to match a pattern. Candidate lengths are bounded
where possible. Unbounded digit runs use possessive repetition, so the engine cannot
reconsider every partition of a long run. Private-key scanning cannot cross another
BEGIN/END delimiter and uses possessive repetition. Adversarial 100 KB inputs have a
one-second test bound, including repeated email fragments, digits and incomplete keys.
This test is a regression guard, not a mathematical performance guarantee for every input.

### Large scans and step 12 performance baseline (2026-09-28)

Card scanning retains at most five digit groups, rejects impossible layouts before
checksumming, and computes each group's two Luhn parity contributions once. Overlapping
windows combine these contributions rather than revisiting every digit. No global cache
retains card text. Group-shaped candidates are still unioned before redaction.

Measured locally with Python 3.13 using `perf_counter` around the pure `scan()` function;
KiB is 1024 characters/bytes for these ASCII fixtures. Before is a single baseline run;
after is the median of three runs. These are engineering measurements, not an SLO:

| Input | Before seconds | Before ms/KiB | After seconds | After ms/KiB |
|---|---:|---:|---:|---:|
| 800 KiB repeated `1 ` | 5.439256 | 6.799070 | 0.177324 | 0.221655 |
| 2 MiB repeated `1 ` | 13.948798 | 6.810937 | 0.456413 | 0.222858 |
| 2 KiB ordinary prose | 0.000153 | 0.076333 | 0.000147 | 0.073312 |

An additional stress case, 2 MiB repeated synthetic `0000 ` groups (many overlapping
Luhn-valid windows), takes 1.912076 s / 0.933631 ms per KiB after optimization.
The original numeric case has a 2-second CI bound at 2 MiB. An authenticated HTTP test
also submits just under the 2 MiB body limit while `/healthz` must finish within 200 ms
of inspection starting, including event-loop scheduling delay.

Inspections totalling **32 Ki characters** or more run via AnyIO's worker-thread pool.
The threshold counts aggregate strings, including nested schema keys, not just the
largest field. This covers chat/embedding input, nonstreaming output and cache hits,
restoration, and end-of-stream detection. Small requests avoid thread-dispatch overhead.
Trace context propagates. Workers are not abandoned on cancellation: request finalization
must not clear the sensitive mapping while a worker still mutates it.

**GIL caveat:** a Python thread is not CPU isolation or a hard scheduling guarantee.
Python work shares the interpreter lock; individual regex operations can hold it, and
many concurrent scans can contend for CPU/pool capacity. Offloading removes the long
synchronous scan from the event-loop task, while layout restrictions bound its costly
search. Step 12 must load-test mixed small/large requests, both numeric stress patterns,
worker saturation, memory and tail latency. These costs are not included in a claim
that all input shapes or arbitrary load can meet the gateway-overhead SLO.

Effective action is the maximum of default, organization and team, ordered
`allow < redact < block`. Defaults block both secret types, redact cards/IBANs and allow
other PII. Credentials should never reach inference; PII can be legitimate task data,
so organizations explicitly choose stricter actions. These defaults are binding even
if an administrator sets `allow`. NULL policies inherit; clear removes overrides.
Set commands replace the scope's entire override list; repeated detector arguments use
the last action. Unknown detector/action/region strings are rejected before mutation.

Migration 0008 stores nullable policy arrays on organizations and teams and a nullable
integer `redaction_count` on receipts. The offline CLI updates the policy and audit chain
in one transaction; the existing key lookup loads immutable policies in the same query.
Changes take effect within the existing verified-key TTL, never extended by a hit.

Placement is authentication → concrete alias resolution and model/residency authorization
→ input inspection → RPM → redacted cache lookup → budget/TPM/lease → provider.
Scan all message roles, text parts, refusals, tool-call arguments and embedding strings.
Tool JSON is decoded for inspection, including unicode escapes, and re-encoded only when
changed. Tool descriptions, schemas and namespaced option text are also inspected;
non-serving provider options are conservatively inspected too. Images, audio and files
are not decoded or scanned. Integer embedding token IDs cannot be interpreted without
the provider's tokenizer and remain unscanned, like encoded/obfuscated text.

Collect every detector finding before deciding to block. Input blocks return
`400 invalid_request_error / guardrail_blocked`, listing types only. No rate admission,
provider call or usage record follows. When redacting overlapping spans, prefer the
earliest, longest span; blocking findings always win regardless of overlap. All detector
findings count in telemetry, while `redaction_count` counts actual input replacements,
including repeated occurrences, on each attempt or cache-hit receipt.

Use bounded direction/detector/action metric labels, count-only input/output spans and
one `guardrail_findings` log event at request finalization, including blocked requests.
No mapping, matched value or generated text enters those systems.

## Consequences

Pattern matching has both false positives and false negatives. It does not recognize
names, postal addresses, encrypted/base64 data, spelling variations such as “at” in email,
or every vendor's current/future secret format. A valid checksum is not proof of PII.
Phone patterns in particular also recognize some order numbers. Full private-key blocks
are detected, incomplete fragments are not. This is neither prompt-injection detection
nor content moderation. Presidio/NER could add contextual detection in a future step.

## Alternatives considered

- ML or an external detection service: excluded by scope, extra latency and data sharing.
- Team replacement or union: would permit weakening organizational protections.
- Scan only user messages: would miss tool results, history and system instructions.
- Log matched examples for debugging: would turn the protection itself into a leak.
