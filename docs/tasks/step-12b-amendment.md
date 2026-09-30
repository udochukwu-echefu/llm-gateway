# Step 12b amendment: exact RPM limiting and a sound benchmark campaign

This amends `docs/tasks/step-12b-load-test.md` on the same branch
(`feat/step-12b-load-test`). Where they conflict, this file wins.

## Why

The first campaign was run honestly, but three flaws in the original spec made most of
its verdicts meaningless:

1. **Too few samples.** S1 started at 1 request/s for 60 s (about 60 requests). The p99 of
   60 samples is essentially the single slowest request, and cold paths (key-cache
   refresh every 30 s, budget rebuilds) dominate it. The ramp stopped at that first
   stage, so capacity was never measured, and S2/S4/S7 were blocked because they depended
   on S1 passing.
2. **Coarse histogram buckets.** `lgw_gateway_overhead_seconds` jumps from 10 ms to 25 ms,
   exactly at the SLO boundary, so a p99 like "23.48 ms" only means "at least 1% of
   requests fell somewhere in 10-25 ms". Meanwhile S5 and S6 at 5-50 req/s measured
   p99 of about 9.6 ms, so the gateway may well meet its target.
3. **An impossible exactness requirement.** S6 demanded exact rolling-minute enforcement,
   but step 6 chose the sliding-window *counter*, which is an approximation by design.
   Under saturation it admitted up to 968 requests in a rolling minute for an RPM of 600
   (1.6x).

## Part A: exact request-rate limiting (GCRA)

- **feat(limits): replace the RPM sliding-window counter with GCRA** (Generic Cell Rate
  Algorithm), in a single atomic Lua script like the others. Emission interval
  `T = 60 / rpm` seconds, burst tolerance `B` requests (`GATEWAY_LIMITS__RPM_BURST`,
  default `max(1, ceil(rpm * 0.05))`). Its guarantee: in **any** interval of length W,
  admissions are at most `W / T + B`. So any rolling minute admits at most `rpm + B`.
  Use Redis `TIME` inside the script, so replicas with slightly different clocks can't
  disagree.
- `Retry-After` and the `x-ratelimit-*-requests` headers come from GCRA's own state
  (the time until the next conforming request).
- **TPM stays on the sliding-window counter** (tokens are only known after the response).
  State plainly in ADR 0010 that TPM is approximate, with the measured overshoot from
  the first campaign as evidence.
- Tests: a **property test** with a simulated clock and random/bursty arrivals, asserting
  that every rolling 60 s window admits at most `rpm + B`; the two-replica race test
  still admits exactly the allowed amount; Redis-down fail-open/closed unchanged.
- Update ADR 0010 (amendment section) and the architecture doc. Explain GCRA in plain
  words: each request "books" the next free time slot, and a request is admitted only if
  its slot isn't too far in the future.

## Part B: measurement fixes

- **fix(observability): finer buckets around the SLO** for `lgw_gateway_overhead_seconds`
  and `lgw_time_to_first_byte_seconds`: at least 0.0005, 0.001, 0.002, 0.003, 0.004, 0.005,
  0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.05, 0.1, then the existing larger ones. Keep
  label sets unchanged. Update the dashboard/alert queries if they depend on the old
  buckets, and `promtool` must still pass.
- **Exact per-request overhead:** add `overhead_ms` (and `key_cache` = hit/miss) to the
  access log line. Benchmark percentiles come from these exact values for the measured
  window. Prometheus histogram estimates are reported alongside, with the difference
  explained.

## Part C: campaign redesign (replaces section 2's thresholds and dependencies)

- **Warm-up:** each run starts with 30 s of traffic that is excluded from measurement.
- **S1 ramp (one replica):** stages of 10, 25, 50, 100, 200, 400, 800 req/s. Each stage
  lasts `max(60 s, 3000 / rate)`, so every stage has at least 3000 measured requests.
  **Don't stop at an overhead miss.** Continue until errors exceed 1% or the client p99
  exceeds 5x the fake-provider baseline (saturation). Report per stage: overhead
  p50/p95/p99 (exact), client p99, throughput, error rate, CPU and memory.
  - **SLO capacity** = the highest stage with exact overhead p99 < 10 ms and errors
    < 0.1%.
  - **Saturation throughput** = the highest stage with errors < 0.1%.
- **S3:** the same ramp on two replicas behind nginx. Scaling factor = two-replica
  saturation throughput divided by one-replica saturation throughput.
- **S2, S4, S7 always run** at a declared rate: 50% of S1's SLO capacity, or 50 req/s if
  no SLO capacity was established. Record which rule applied.
- **S6:** rerun after Part A with RPM=600 and 50 req/s across two replicas. Report the
  maximum admissions in any rolling 60 s window, and assert it's at most `600 + B`.
- **Idle-path report:** 1 req/s for 5 minutes (about 300 samples). Report the overhead
  distribution split by `key_cache` hit/miss, to explain cold-path tails. It's
  informational and has no SLO verdict.
- Repetitions: 3 for S1, S3 and S6; 1 each for S2, S4, the idle path and the 10-minute
  S7 soak (time budget).
- At the end, stop every load-test container (`docker compose --profile loadtest down`).

## Report

Rewrite `docs/benchmarks/load-test-report.md` around the new campaign. Keep a short
section on the first campaign and why it was redesigned, since that's valuable evidence
of method. Update the README "Performance" section and the roadmap. If all scenarios ran,
mark step 12 done.
