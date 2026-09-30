# Step 12b: Load test, benchmark report and deployment notes

- **Branch:** `feat/step-12b-load-test` (from `main`)
- **Read first:** `AGENTS.md`, `docs/architecture.md`, all ADRs,
  `docs/security/threat-model.md`, `docs/roadmap.md`, this spec
- **Needs:** Docker running (Postgres, Redis, and the images below)

## Goal

Every step so far was verified for **correctness**. This final step measures the gateway
under sustained load and answers, with numbers, the questions an operator or interviewer
will ask: How much latency does the gateway add? How much traffic can one replica take?
Does it scale to two? Does it lose accounting data or leak memory over time? Do the
limits stay exact under pressure?

The primary target, set in step 1's roadmap: **gateway overhead under 10 ms at p99**.
"Overhead" is the `lgw_gateway_overhead_seconds` metric from step 8: time added by the
gateway on top of waiting for the provider.

## Part 0: Housekeeping (do these first, each as its own commit)

1. **fix(tests): make the budget-rebuild deadline test deterministic.**
   `tests/limits/test_service.py::test_slow_budget_rebuild_has_one_total_deadline` is
   flaky. With `rebuild_timeout=0.04`, the real Redis lock round trips can use up the
   whole 40 ms before the stubbed spend query runs, so `entered` is never set (it failed
   once on `main` in a slower sandbox while the gateway behaved correctly). Fix the
   test, not the product: warm the Redis connection before timing, use a comfortably
   larger `rebuild_timeout` (e.g. 0.5 s) so the deadline always fires *inside* the
   blocked spend query, and replace the tight `< 0.3` bound with a generous one relative
   to the timeout. Run the test 20 times in a row and report that it passed every time.
   Then look for other tests that use tight wall-clock limits (under about 1 s) and fix
   them the same way, or report why they're safe.
2. **docs(agents): record the sandbox workarounds and the timing rule in `AGENTS.md`.**
   Add a short "Sandboxed environments" section: when `uv run` can't write its cache,
   use `.venv/bin/ruff`, `.venv/bin/pytest -p no:cacheprovider` and
   `.venv/bin/pyright --pythonpath .venv/bin/python`. Add to "Tests": *"Never assert
   tight wall-clock bounds. Assert ordering or behaviour, and keep only a generous time
   limit as a safety net."*

## Decisions already made (binding; object in your report if you disagree)

### 1. A controlled, repeatable setup

- **A fake provider**, not real providers: free, repeatable, and it isolates the
  gateway's own cost. Put it in `loadtest/fake_provider/`: a small async
  OpenAI-compatible server with configurable latency (`FAKE_LATENCY_MS`), streaming
  (configurable chunk count and interval), usage in responses, and embeddings. Measure
  its own latency first and include it in the report, so it can't be the hidden
  bottleneck.
- **k6** (Docker image `grafana/k6`, pinned version) drives the load. Scripts in
  `loadtest/k6/`. No new Python dependencies in the project.
- A compose profile `loadtest` containing: the fake provider; **two** gateway replicas
  built from the repo's Dockerfile, with provider base URLs pointing at the fake
  provider and a real catalogue model name (e.g. `groq/openai/gpt-oss-20b`); an **nginx**
  load balancer (pinned) in front; plus the existing Postgres, Redis and Prometheus.
  Single-replica scenarios target one replica directly.
- A setup script creates the load-test org, team and key through the CLI and writes the
  key to a git-ignored file. It's never printed or committed.

### 2. Scenarios

Run each scenario **3 times** and report the median run. Record gateway overhead
p50/p95/p99 from Prometheus (aggregated across replicas), client latency p50/p95/p99
from k6, throughput, error rate, and container CPU and memory.

| # | Scenario | What it answers |
|---|---|---|
| S1 | Non-streaming chat, fake latency 200 ms, **ramp up** on one replica until overhead p99 > 10 ms or errors > 0.1% | Max sustainable throughput per replica within the SLO |
| S2 | Streaming chat (20 chunks over ~1 s) at 70% of S1's max | Time-to-first-byte overhead and stream stability |
| S3 | S1's load shape against **two replicas behind nginx** | Scaling factor (ideal = 2×) |
| S4 | S1 at 70% load with ~5 KB PII-rich prompts (guardrails redacting) | Cost of guardrails |
| S5 | Repeated identical embeddings (cache hits) | Cache hit latency and ratio |
| S6 | Team RPM limit = 600 across both replicas, driven well above it for 3 minutes | Limits stay **exact** under load: admitted per window = the limit, no over-admission |
| S7 | **Soak:** 10 minutes at 70% of S1's max on two replicas | No memory growth trend, **usage records == successful provider-bound requests** (zero drops), queue depth stays low, zero errors |

### 3. Profiling and honesty

- Profile one S1 run with **py-spy** (via `uvx py-spy`; run a replica locally if
  ptrace isn't available in Docker). Commit the flame graph SVG to `docs/benchmarks/`,
  and name the top hotspots.
- **Don't optimise in this step**, unless a fix is tiny, clearly safe, and shown with
  before/after numbers in its own commit. Otherwise, list recommendations ranked by
  expected impact (e.g. uvloop/httptools, a faster JSON library, more workers per
  container, and which hot paths, if any, would justify a Rust extension). Measure
  first, then decide.
- If an SLO isn't met, say so plainly and explain why. A missed target with a clear
  explanation is a better portfolio artefact than an unexplained number.
- Caveats in the report: laptop hardware, Docker Desktop's virtualisation overhead, and
  a fake provider (real providers add network variance but not gateway overhead).

### 4. Deliverables

- **`docs/benchmarks/load-test-report.md`:** environment (CPU model, cores, RAM, Docker
  Desktop resource limits, OS, image versions, git commit), method, a results table per
  scenario, charts, the flame graph, findings, SLO verdicts, and recommendations.
- **Charts** as PNG in `docs/benchmarks/`, generated from k6's JSON output by a script
  (`loadtest/charts.py`, run with `uv run --with matplotlib ...`; matplotlib must NOT
  become a project dependency).
- **`loadtest/README.md`:** how to reproduce every scenario with one command each.
- **`docs/deployment.md`:** a short production checklist. Stateless replicas behind a
  load balancer; the migration step; readiness vs liveness probes; secrets via the
  secret store; keep the admin API and metrics ports private; Grafana authentication;
  TLS at the edge. Also a clearly marked **unverified** note: Kubernetes mounts secret
  volumes with directory mode `1777`-style permissions, which the file secret store's
  directory check may reject even with `defaultMode: 0400`. Verify this in a real
  cluster before relying on the file backend there.
- **CI:** a k6 **smoke** job (about 30 s at low load against one replica and the fake
  provider) with loose thresholds (zero errors; overhead p99 under a generous bound such
  as 50 ms), so regressions are caught without flaky CI.
- **README:** a "Performance" section with the headline numbers and a link to the
  report. **Roadmap:** step 12 done, all steps complete.
- **`docs/architecture.md`:** a "Step 12b" section in plain language: what load testing
  and a soak test are, why we use a fake provider, why p99 and not the average, how to
  read a flame graph, and what "scaling factor" means.

## Out of scope

Real-provider load tests (cost, and they measure the provider, not us), autoscaling,
multi-region, performance optimisations beyond tiny safe fixes, and a "How this project
was built" README section (the owner will add it later).

## Report back with

- The final output of the four gates and the db and redis tests, plus the 20× run of the
  fixed test.
- The results table for S1 to S7, with SLO verdicts.
- The top 3 hotspots from the flame graph, and the ranked recommendations.
- Anything you couldn't run, and why.
- `git log --oneline main..HEAD`.
