# ADR 0017: Reviewed aliases with weighted concrete destinations

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Clients need stable model names while platform teams change providers or trial a new model.
The trial must remain attributable and cannot bypass organization or team access rules.

## Decision

Add aliases to catalog/models.toml, reviewed alongside prices and fallback approvals.
Names match ^[a-z][a-z0-9-]{0,31}$ and cannot equal a known provider. Each nonempty target
list contains only unique concrete catalogue IDs of one kind, with strict positive integer
weights. Aliases cannot target other aliases. Startup rejects invalid declarations.
The reviewed defaults are fast (Groq GPT OSS 20B / DeepSeek Flash, 90/10), smart (Groq
GPT OSS 120B), and embed (Gemini Embedding 2). No fallback defaults change.

Remove targets forbidden by organization intersection team before choosing. If none remain,
return 403. Also remove unconfigured providers and targets without an active price; if
permissions allow targets but none are available, return 404 model_not_found. Renormalize
weights over remaining targets. An injected independent random source draws once per client
request, without stickiness or cost/latency feedback. Breaker state is handled by the existing
recovery layer after selection, not used to silently change trial weights.

The selected concrete model becomes the original model for retries and fallback. Existing
response model transparency and fallback headers remain concrete. Add x-lgw-alias on
resolved alias responses, including streams and errors. Each attempt's usage receipt has
a nullable alias column (migration 0006); retries and fallback retain the original alias.
lgw_upstream_requests_total adds alias: only reviewed names or the empty string for direct
requests. Failed/unknown client names and provider-returned text cannot become alias labels.
SQL can group costs and durations by alias/provider/model; Grafana can compare request counts.

Unknown names without a slash return 404 model_not_found and list only aliases with at
least one permitted, configured, currently priced target. /v1/models uses the same rule;
alias entries use owned_by=gateway. CLI effective lists describe catalogue permissions,
independent of the running gateway's provider credentials and current price availability.

## Consequences

90/10 describes expected proportions over many independent draws, not a promise for ten
requests. Filtering permissions or disabled providers changes those proportions; operators
must account for this when comparing trial cohorts. Switching providers shares content with
another company and needs reviewed approval. Historical receipts retain the alias and
catalogue version, so changing a target does not rewrite trial history. Metrics count
attempts, including retries; use SQL for per-client-request analysis. No dependency is added.

## Alternatives considered

- Alias chains: ambiguous authorization and harder review.
- Duplicate targets: unnecessary ambiguity; combine their weights into one entry instead.
- Mutable runtime aliases: bypasses the catalogue review trail.
- Random selection before permission filtering: creates avoidable intermittent denials.
