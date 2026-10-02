# Runna Gateway — 2–3 minute walkthrough

Aim for about 2 minutes 45 seconds at a natural pace. Show synthetic records only.
Use the read-only tour for the console; use the offline tests below for the failure
demonstration. The tour cannot change policies or trigger paid provider calls.

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Current split-theme sign-in, then the platform Overview | “Calling a model is easy. Managing credentials, permissions, spending and provider failures across several applications is harder. I built Runna Gateway to put those decisions behind one OpenAI-compatible API. This is my own portfolio project; everything in this public tour is synthetic.” |
| 0:20–0:55 | Overview; open the account menu; switch to Northwind Health | “Applications use team keys instead of receiving provider credentials. The console gives operators a view of usage and controls. This profile sees every organisation. Switching to Northwind changes the authenticated session and reloads the workspace with only Northwind’s records. Both public profiles are read-only, and the API enforces that restriction.” |
| 0:55–1:15 | Requests and a receipt detail, then a team’s Policies tab | “Requests stores metadata, not conversations. Unknown model prices stay unpriced instead of appearing free. Here, policy inheritance shows the organisation rule, the team override and the effective result. A team can narrow access; a provider outage must never widen it.” |
| 1:15–1:40 | Run the three offline regression tests below; show the test names and real result | “This failure demonstration uses mocked providers. It checks approved fallback order, rejects ineligible targets, and proves that a failure after streaming has started does not splice another model’s answer into the stream. Retries are bounded, and read-timeout retries are disabled by default because a timeout does not prove the upstream stopped working.” |
| 1:40–2:10 | Benchmark report: dropped-iteration warning and rolling-RPM section | “The first benchmark was too easy to misread. A tempting scaling result included almost fifteen thousand requests the generator never sent. I excluded that stage. Load also exposed a minute-boundary bug in the rate limiter. I replaced the weighted counter with Redis-backed GCRA. Three runs stayed below the expected rolling bound, and restoring the old counter made the regression fail.” |
| 2:10–2:45 | Selected benchmark table, architecture diagram and source link | “At the tested latency capacity, overhead p99 was 7.2 milliseconds for one replica and 5.6 for two. Successful throughput doubled from roughly 199 to 399 responses per second at higher stages, which missed that latency target. A ten-minute soak matched all thirty thousand and one successful receipts after flushing. These are laptop tests with a fake provider, not production capacity. Accounting is still best-effort. The source and full measurement limits are linked with the project.” |

## Recording preparation

Start the demo only when recording the tour; a cold visit previously took about
33 seconds. Confirm the URL loads before recording. If the hosted service is
unavailable, use a disposable fake-only local appliance with the same committed
code, and label the footage as local. Do not simulate a passing live visit.

From the repository root, this small failure demonstration is offline and needs
no Docker containers or real provider keys:

```bash
.venv/bin/pytest -q -p no:cacheprovider \
  tests/api/test_resilience_fallback.py::test_fallback_order_and_target_options_are_transparent \
  tests/api/test_resilience_fallback.py::test_fallback_skips_ineligible_target \
  tests/api/test_resilience_retry.py::test_no_retry_or_fallback_after_first_streamed_byte
```

Show the actual output; parameterised cases may produce more than three passes.
Do not display `.env`, cookies, key-creation dialogs or raw provider diagnostics.
After recording, close the browser session and stop only the temporary services
you started. The script is a recording plan; no video has been recorded yet.

Sources: [architecture](architecture.md), [resilience tests](../tests/api/test_resilience_fallback.py),
[benchmark method and limitations](benchmarks/load-test-report.md).
