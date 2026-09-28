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

Review amendment: for space/tab/dash-separated number runs, examine contiguous whole
digit-group windows totalling 13–19 digits. Select non-overlapping Luhn-valid windows,
preferring the most digits, then the earliest start. Each start considers at most 19
groups, so adjacent CVV/expiry/table columns cannot hide an otherwise valid card.
Do not slide inside an unseparated group longer than 19 digits: arbitrary 16-digit
windows pass Luhn about 10% of the time. A card concatenated directly with other digits
without separators remains a deliberate residual gap to avoid flagging tracking numbers.

ReDoS means regular-expression denial of service: an attacker supplies text that makes
an engine try exponentially many ways to match a pattern. Candidate lengths are bounded
where possible. Unbounded digit runs use possessive repetition, so the engine cannot
reconsider every partition of a long run. Private-key scanning cannot cross another
BEGIN/END delimiter and uses possessive repetition. Adversarial 100 KB inputs have a
one-second test bound, including repeated email fragments, digits and incomplete keys.
This test is a regression guard, not a mathematical performance guarantee for every input.

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
