# ADR 0027: Metadata-only operations console and safe exports

- **Status:** Accepted
- **Date:** 2026-10-01

## Context

Operators need to investigate failed calls and slow providers without retaining sensitive
prompts. Billing summaries alone cannot describe recovery attempts or latency tails.
Configuration and downloadable spreadsheets introduce separate disclosure risks.

## Decision

Expose org-scoped request receipts through a strict filter contract, newest first, with
stable `(created_at, id)` seek cursors and a maximum page size of 200. A request detail
returns every recorded attempt in order. The log remains metadata only. Indexes cover
org/time pagination, org/request/attempt timelines, and key/time activity lookups.

Use a separate analytics endpoint rather than extending billing-oriented `/usage`:
Postgres `percentile_cont` computes p50/p95/p99 for duration and first byte over recorded
attempts, including recovery attempts. These are not the gateway-overhead SLO. Request,
retry, fallback and cache counts retain receipt semantics; absent timing and savings stay
unknown. Buckets use UTC and are grouped by provider, concrete model or team.

Build platform settings from named allowlisted fields of the effective runtime configuration.
Never dump the settings object. Show provider key presence as a boolean, and base-URL hosts
without paths or credentials. The serving replica supplies its own in-process circuit state,
clearly labelled “this replica”; usage-derived health covers 15 minutes and 24 hours.
Settings stay read-only because environment configuration changes through reviewed deployment.

Every BFF query has an operation-specific strict schema. Search scopes orgs, teams and keys
in SQL before limiting results; client filtering is an additional guard. The credential
and all gateway calls remain server-only. CSV exports use the same credential redaction,
stream pages under a 10,000-row cap, quote every cell, escape quotes, and prefix potential
spreadsheet formulas with an apostrophe, including whitespace-prefixed formulas. Numeric exports round to three decimal places; money rounding uses exact decimal
arithmetic. API responses and UI money tooltips retain exact decimal strings. UI arithmetic uses BigInt; half-up display rounding
shows two decimals or up to four significant digits below one cent. Exact values are in
tooltips. A nullable budget display column preserves the administrator's original input
alongside its numeric accounting value.

Filters and sorting live in URLs. Client tables sort their loaded rows and explicitly
say so for the potentially large request log; cursor “Load more” adds earlier rows. Theme,
time zone, density and landing preference live only in browser storage. CSP permits no
inline script/style additions. Native dialogs retain focus containment and Escape.

Demo receipts are deterministic synthetic history at today's reviewed rates, not invoices
or proof of provider capabilities. Recovery chains are illustrative, not new fallback
configuration. Northwind's historical traffic predates the current EU-only restriction:
no reviewed model currently qualifies for EU inference. Audit events use the real service
and current timestamps; the chain API has no supported backdating input. Seeder opt-in
and an actual bound-engine loopback/compose-host check both precede database I/O. Secrets
for two synthetic admin sign-ins rotate into an ignored mode-0600 file on each run.

## Consequences

Metadata and exports still reveal operational activity, so the private listener and
org-scoped authorization remain essential. Recorded attempts are best-effort receipts;
unknown costs and dropped receipts prevent invoice-level certainty. Search results are
bounded to 30; tables can load more. Browser preferences may briefly follow the system
before hydration, since an inline bootstrap would violate the existing CSP. Budget
refusal applies to known priced costs; unpriced destinations need model restrictions.

## Alternatives considered

- Retain prompts for debugging: rejected because it expands the sensitive-data boundary.
- Add latency fields to billing usage: rejected because time buckets and attempt grouping
  are different from billing summaries and stable billing pagination.
- Serialize Settings and redact afterward: rejected because new fields can leak by default.
- Edit environment settings through the console: rejected in favour of reviewed deploys.
- Float money or unsafe CSV formulas: rejected because accounting must remain exact and exports safe.

## Review amendment: latency comparison

Use native legend buttons with aria-pressed to select visible series and compute the axis
from that selection. Offer base-10 log scaling only for latency. The lower bound is the decade at or below
the smallest positive visible value, up to 1 ms. Zero timings are gaps. Positive sub-millisecond values stay within the plot
and their axis ticks retain enough precision to avoid a misleading zero label. Tick labels
include duration units. The table remains the complete alternative. Use local generated tours and curated README images to bound Git
growth; retain the cleanup backup branch until review approval.
