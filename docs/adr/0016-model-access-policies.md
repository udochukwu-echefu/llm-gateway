# ADR 0016: Organization and team model access intersect

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

Catalogue approval alone does not authorize every team to send data to every provider.
Aliases and outage recovery can change the destination after the client names a model.

## Decision

Store nullable arrays of model patterns on organizations and teams. NULL at organization
level allows every catalogued model; NULL at team level inherits the organization policy.
An explicit empty array denies all. A model must match both non-NULL lists: organization
intersection team. A team cannot widen its organization's access, even with provider/*.
Patterns are exact provider/model IDs or provider/* and each must match the reviewed
catalogue when set. Duplicate patterns are normalized without changing their order.

Key lookup joins both policies in the existing database query and puts immutable tuples
in the verified-key cache. The cache's original TTL bounds policy-change delay; hits do
not extend it. Authentication and failed-authentication IP controls still run first.
Chat and embedding routes resolve an alias and authorize its concrete destination before
budget, RPM, TPM or concurrency admission. Denial is 403 invalid_request_error with code
model_not_allowed; it names the denied model without disclosing allowed alternatives.
GET /v1/models filters concrete models and aliases by the same policy and retains its
existing limits admission. Every fallback is separately filtered before capability checks
or provider execution. A forbidden fallback is skipped, not a new client 403; an open
primary with no remaining alternative returns 503 provider_unavailable.

Offline set-models and clear-models update their owner and append an audit event in one
transaction. Details contain only validated, comma-separated catalogue patterns under
allow (empty details for clear). show-models is read-only, reports both policies and
their effective catalogue models/aliases, and explains that runtime provider availability
also applies. All commands state the cache-delay limitation.

## Consequences

A restrictive change can take up to the configured cache TTL on each replica. Organization
wildcards also authorize new models added later for that provider, so catalogue review
remains a security boundary. Removing a model from the catalogue can leave an old pattern
matching nothing; runtime intersection still denies it. No per-key scopes are introduced.
Allow-by-default preserves existing tenants' behavior; operators must set an org policy
when they want a restrictive default. Migration 0006 preserves existing access with NULL.

## Alternatives considered

- Union or team replacement: lets teams bypass organization restrictions.
- Check only the client name: aliases and fallback bypass the restriction.
- Limits before policy: spends capacity and may return 429 instead of a policy denial.
