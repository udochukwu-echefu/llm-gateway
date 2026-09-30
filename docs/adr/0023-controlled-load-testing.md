# ADR 0023: Isolated fake-provider benchmarks and fail-closed evidence

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

Real model latency varies and costs money. A throughput figure is misleading unless the
load generator, upstream and measurement windows are controlled. Local credentials must
never reach providers or benchmark artifacts.

## Decision

Use the binding step 12b topology: k6 1.3.0, an async synthetic OpenAI server, two
single-worker gateway containers and nginx 1.28.0-alpine. Reuse Postgres 17.6, Redis
7.4.5 and Prometheus 3.2.1. Use a separate benchmark database and Redis DB 14.
Only the benchmark's internal Docker network connects the replicas and provider: no
external egress. The orchestration ignores `.env` and inherited gateway configuration.
Generate temporary pepper/cache keys and CLI-issued client keys in mode-0600 files
inside a git-ignored mode-0700 directory. Never print CLI output containing credentials.

Use open-loop constant arrival-rate plateaus, increasing until either the overhead or
error target fails. A dropped k6 iteration is load-generator insufficiency, not a
successful request. Keep all three repetitions and select the median by the scenario's
primary metric; do not combine independently selected percentiles into an imaginary run.
Aggregate histogram buckets across the tested replicas before estimating quantiles.
Histogram quantiles are bucket-interpolated estimates, not exact request percentiles.

Correlate the soak's fresh team's durable receipts with successful provider completions
after allowing the writer to drain. Expected RPM 429s are separate from availability
errors. Inspect every observed fixed-minute bucket and the weighted previous/current
admission rule; do not replace the product's sliding-window algorithm to improve a report.
No performance optimization or new project dependency is part of this decision.

## Consequences

Laptop results include Docker Desktop and shared-resource contention and do not certify
production capacity. A fake server removes model variability but still has measurable
network/server costs. Thirty minutes of soak data cannot prove a leak never exists.
Raw local artifacts stay ignored; publish only metadata, charts and a stack-only profile.

## Alternatives considered

- Real-provider load: incurs charges and measures somebody else's variability.
- Closed-loop VUs only: slow responses reduce offered load, hiding overload.
- Rewriting RPM as a fixed window: changes accepted policy instead of measuring it.
- Declaring an unrun scenario successful: not evidence.

## Campaign amendment (2026-09-30)

The step-12b amendment supersedes the original stopping rules and dependencies.
Warm each run with 30 seconds at its offered rate, then exclude those requests
using distinct request-ID prefixes. Exact access overhead is the verdict input;
histogram deltas remain a corroborating estimate with count-coverage validation.
Ramp 10, 25, 50, 100, 200, 400, 800/s with at least 3000 scheduled requests per
stage. Continue after overhead misses; stop on >1% errors, client p99 >5 times
the measured fake baseline, or incomplete telemetry. Dropped iterations are retained but do not alone stop
the ramp. Keep the stopping
stage. SLO capacity uses <10 ms exact p99 and <0.1% errors; saturation throughput
uses <0.1% errors. Select a whole median ramp by saturation throughput.
S2/S4/S7 always run at half S1 SLO capacity, or 50/s if none exists. Run S1/S3/S6
three times, S2/S4/idle/S7 once, retaining S5's original three repetitions.
S6 checks atomic Redis admission timestamps, including its warmup, against 630.
Idle traffic is informational; it has no SLO verdict.

The amendment explicitly authorizes replacing RPM's approximate counter with GCRA
for correctness; the original instruction above to retain that counter is superseded.
The amended soak is one ten-minute run. Error-only saturation throughput follows
the amendment literally, even if k6 could not generate every iteration. Publish the
actual successes/s and the highest eligible fully generated stage separately, so
generator omissions cannot masquerade as capacity. A one-iteration omission caused
an early stop in S3 repetition 3; the existing stages were retained and the missing
higher stages were completed after correcting the runner. No stage was retried to
obtain a better percentile.
