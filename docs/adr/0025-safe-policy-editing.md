# ADR 0025: Safe policy editing with conditional replacement

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

Policy PUT replaces the entire override at one level. Two administrators opening the
same policy can otherwise erase each other's changes. An empty list denies everything,
while a missing override inherits restrictions; confusing them can stop a whole tenant.
Removing a guardrail override can also reduce protection.

## Decision

The private GET /admin/v1/catalog exposes reviewed names, providers, regions, endpoint
kinds, current-price availability and alias targets. It exposes neither credentials nor
provider URLs. Both authenticated admin roles may read it; editing it remains code review.

Each policy GET includes a 64-character SHA-256 version for the selected level's stored
override. Migration 0010 adds a separate monotonically increasing revision for each of the
three policy columns on organizations and teams. The hash covers owner ID, policy kind,
revision and the stored value. It remains stable until that policy is written. A value-only
hash would conflict with the spec's requirement that *every* successful write/clear change
the version: a repeated save would keep it, and change-then-restore could revive an old
version (the ABA problem). Including a stored revision satisfies those safety requirements.

PUT and DELETE optionally accept If-Match: "<version>" for CLI compatibility. The console
BFF requires that header on every policy write, validates its quoted lowercase hex format,
and forwards it only to those endpoints. Writers lock organization then team rows, check
the version, advance the revision, replace/clear the value and append the audit event in
one transaction. CLI writes use the same lock and revision path. A mismatch returns the
standard 412 policy_version_conflict envelope without changing data, revision or audit.

Shared editor components show loaded org/team overrides beside the API's effective result,
and a draft-versus-loaded change summary. No save button appears without a change.
No restriction and deny-all are separate radio choices; an empty selection in the specific
allow-list mode cannot silently become deny-all. All override removals name their level
in a confirmation. Deny-all and any weakened/removed guardrail action need a consequence
confirmation. Lower actions show the default/org floor inline. Per-detector Inherit omits
that detector from the replacing list. Effective models, aliases, regions and actions come
from API views, including residency's usable-model list; the browser never authorizes models.
Residency choices and BFF validation share `catalogRegions`: an optional catalogue `regions`
field is authoritative. Older API responses extend a single five-region fallback with model
regions, retaining valid empty regions such as EU. New advertised identifiers get a neutral
label rather than an invented processing guarantee. A residency PUT first reads the catalogue
server-side, then validates its bounded, deduplicated enum before mutation. Catalogue read
failure blocks the write; the API remains the final authority. No new region is hard-coded.

On 412 the console preserves the draft, disables another save and offers an explicit reload.
It never retries automatically. If a write succeeds but the refreshed API view fails, the
console reports the successful save and requires reload before another write; it does not
claim someone else changed the policy. Reload asks before discarding edits. Shared navigation
tracking warns on tabs, links, sign-out, reload/close and cancellable native browser
traversals. Native dialogs provide focus containment, Escape cancellation and focus return.
Origin checks, CSP and the server-only credential boundary from ADR 0024 remain in place.

Cache purge has an exact-name confirmation for an organization or team. Successful responses
show the removed count; Redis absence, timeout and connection errors return a plain 503.
Purge is best effort: concurrent requests may create new entries during SCAN/UNLINK. It
neither removes usage receipts nor changes policies, and successful purges are audited.

The Overview addition uses existing scoped organizations, teams, keys, usage, budgets and
audit endpoints, exhausting pagination before totals and rankings. Money uses pico-dollar
BigInt arithmetic. Requests retain the API's provider-attempt/cache-hit accounting semantics;
tokens show known totals and a partial flag, with unpriced requests and savings explicit.
Recent events are the last five IDs after exhausting the ascending audit API. No extra
Overview endpoint is introduced. Large audit histories may justify a separately reviewed
reverse-page API later. The local Demo Co seeder is opt-in, repeatable and entirely synthetic;
its generated key secrets are discarded and never printed.

## Consequences

Read versions describe this level's stored override, not every inherited policy/catalogue
change. Runtime enforcement still follows the existing verified-key cache TTL, normally
30 seconds per replica. Organization-first locks serialize team policy writes inside an
org; these low-volume administrative writes favor correctness over maximum throughput.
UI confirmations prevent mistakes, not crafted API calls. The API remains the role/scope,
validation and concurrency authority; unconditional authorized CLI writes remain supported.
Native browser warning support can vary; the application always guards its own navigation
controls and installs beforeunload for document exits.

## Alternatives considered

- Value-only hashes: cannot invalidate repeated writes or detect ABA changes.
- Check then write in separate transactions: permits both racing writers to pass.
- Automatic conflict retries: silently overwrites someone else's policy.
- Client-computed effective access: can drift from catalogues, defaults and API enforcement.
- Confirm every ordinary edit: adds friction without explaining the dangerous cases.
- Fake EU processing labels: rejected; EU-only correctly permits no current reviewed model.
