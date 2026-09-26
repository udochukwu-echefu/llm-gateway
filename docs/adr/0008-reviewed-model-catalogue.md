# ADR 0008: Reviewed model catalogue and exact USD arithmetic

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

Budgets and historical spend require an explicit answer to which model was used and
what each token cost at request time. Provider prices and token shapes change.

## Decision

Keep the allowlist and prices in `catalog/models.toml`, validated at startup. Price
changes are reviewed in git instead of edited in a database: finance can audit a
diff and a commit. Reject unlisted provider/model/kind combinations before contacting
the provider. List only enabled providers' catalogued IDs through authenticated
`GET /v1/models`. Each row records the catalogue version and its computed cost;
historical costs are never recalculated.
Each model has a nonempty, strictly increasing list of price periods. A period
starts at midnight UTC on `effective_from`; select it once at request time,
before sending to the provider, and retain it even if a stream crosses midnight.
Models with no period in force yet are unavailable. Announced future prices can
be reviewed and deployed ahead of time; Gemini 3.8 Flash doubles its published
standard rates on 2027-01-01, so both periods are already in the catalogue.

Store USD prices and costs as `Decimal`, with `NUMERIC(20,12)` in Postgres. For each
million tokens, charge `(prompt - cached) * input_price + cached *
(cached_input_price if present else input_price) + completion * output_price`,
divided by 1,000,000. Reasoning tokens are part of completion tokens, not charged
twice. Embeddings use input only. Provider adapters normalize usage first.
DeepSeek's cache-hit fields become canonical cached input. Gemini's observed
OpenAI-compatible usage includes hidden output in `total_tokens` but not always
in `completion_tokens`: charge the difference at the output rate, leaving
`reasoning_tokens` NULL unless the provider explicitly reports it.

## Consequences

An unknown model is unavailable even if a provider supports it; a newly published
price needs a code review and deployment. USD is explicit in each entry. The reviewed
prices are standard paid API rates, not batch or priority rates. DeepSeek publishes
peak and off-peak schedules: this catalogue's **peak** rate is a conservative cost
estimate, not the invoice amount at off-peak times. Effective **dates** cannot
represent hour-of-day schedules; add time-of-day/holiday-aware pricing as a
future catalogue feature before treating DeepSeek estimates as exact invoices.
Google's current official pricing page has no
`gemini-embedding-001` row, so this model is excluded instead of inventing a price.
Gemini Embedding 2 is priced for text input only; its multimodal rates differ
and are outside this text-only embedding API.

## Alternatives considered

- Price table in Postgres: rejected; unreviewed edits could silently change spend.
- Float prices: rejected; decimal fractions are inexact in binary floating point.
- Guessing prices for models without official pricing: rejected.
