# Reproduce the benchmarks

Requires Docker Desktop running and `uv sync`. No real providers are called, no `.env`
is read/copied, and no project dependency is added. Use the commands from the repo root.
Do not run scenarios concurrently: they share replicas, provider counters and Prometheus.

```bash
uv run python -m loadtest.run setup
uv run python -m loadtest.run provider --skip-setup
uv run python -m loadtest.run S1 --skip-setup
uv run python -m loadtest.run S2 --skip-setup
uv run python -m loadtest.run S3 --skip-setup
uv run python -m loadtest.run S4 --skip-setup
uv run python -m loadtest.run S5 --skip-setup
uv run python -m loadtest.run S6 --skip-setup
uv run python -m loadtest.run S7 --skip-setup
# Or setup plus all scenarios, sequentially:
uv run python -m loadtest.run all
```

Every run starts with 30 seconds of traffic excluded from measurement. S1/S3
ramp through 10, 25, 50, 100, 200, 400 and 800 requests/s. Each plateau lasts
max(60 seconds, 3000 / rate), ensuring at least 3000 scheduled measured requests.
Overhead misses do not stop the ramp. Stop when errors exceed 1%, client p99
exceeds five times the measured direct-provider p99, or generation/telemetry is
incomplete. Keep the stopping stage and all repetitions.

SLO capacity is the highest offered stage with exact overhead p99 <10 ms and
errors <0.1%. Saturation throughput is the successful throughput of the highest
stage with errors <0.1%. The two-replica/one-replica saturation throughput ratio
is the scaling factor. If the 800/s ceiling is reached, capacity beyond it is
unmeasured. Median ramps are selected by saturation throughput, ties by repetition.

S2/S4/S7 always run at floor(50% of S1 SLO capacity), minimum 1/s, or fallback
50/s if S1 found no SLO capacity. The result records which rule applied. S1/S3/S6
run three times; S2/S4/idle/S7 once. S5 retains three repetitions at 5/s. S6 uses
50/s for 180 measured seconds across two replicas, RPM=600, default B=30; atomic
Redis admission timestamps (including warmup) must respect a rolling bound of 630.
S7 holds the declared rate for 600 measured seconds. Idle is informational: 1/s
for 300 measured seconds, with hit/miss overhead distributions and no SLO verdict.
Run it with `uv run python -m loadtest.run idle --skip-setup`.

Stop all profile containers at the end (preserve volumes and raw evidence):

```bash
docker compose --env-file /dev/null --profile loadtest down
```

`loadtest/.state/` (0700) contains generated runtime credentials and one CLI-issued
key per run (0600). It is ignored by git. Credentials are never printed, passed in
process arguments, or included in results. A fresh org/team each run avoids stale
policies, counters or caches. The database is `gateway_loadtest`; Redis DB 14 is used,
not the owner's runtime DB 0 or test DB 15. No database/counter reset or deletion occurs.
The fake upstream and replicas have only an internal Docker network. nginx provides
loopback diagnostic access for the host; k6's one-replica traffic bypasses nginx.
Prometheus uses `loadtest/prometheus/prometheus.yml` with one-second scrapes.

The setup script calls the real `gateway-admin` CLI with captured output, then writes
the key privately. To start the profile manually **after setup**, use:

```bash
PROMETHEUS_CONFIG_DIR=./loadtest/prometheus docker compose --env-file /dev/null --profile loadtest up -d
```

## Evidence and interpretation

Every plateau has k6 `points.json`, `summary.json`, and `measurement.json` under the
ignored `loadtest/results/`. These contain aggregate/point metrics only, never request
headers or payloads. Keep all repetitions, including failed plateaus. Prometheus
histogram bucket deltas are aggregated over the selected replicas before interpolating
p50/p95/p99. They are estimates, not exact request timings. Exact overhead_ms percentiles come
from access logs with a unique per-run request-ID prefix. Warmup has a distinct
prefix and is excluded. Both access and histogram counts must match k6 requests
for a complete measurement. The profile enables JSON access logs at INFO. Client latency is k6's full
HTTP duration; streaming TTFB is reported separately. SSE validation checks 20 content
chunks, usage, DONE and no error event. Expected RPM 429s are not availability errors.

Container CPU and memory are sampled about every five seconds using `docker compose
stats` (all services; some Compose versions accept only one service argument).
Sampling failure is explicit, not a zero. Queue depth is sampled from Prometheus
at two-second resolution. After a final scrape/writer wait, fresh-team usage counts are
compared with client successes and completed fake-provider requests. The report must
not claim zero lost receipts merely because the queue is empty.

## CI smoke

`uv run python -m loadtest.run smoke --skip-setup` runs one 30-second,
5-request/s measurement and fails for errors, dropped iterations, missing overhead or
overhead p99 >=50 ms. CI uses a single 30-second repetition (see the workflow).

## Charts and profile

```bash
uv run --with matplotlib python -m loadtest.charts
```

Matplotlib is ephemeral, not in `pyproject.toml`/`uv.lock`. Profile with `uvx py-spy`
using this extra S1-shaped diagnostic run:

```bash
uv run python -m loadtest.profile
```

It builds an ephemeral py-spy 0.4.2 image, joins only the fake-key replica's PID
namespace with `SYS_PTRACE` and `seccomp=unconfined`, and disables its network. These
debugging permissions are **not** applied to the production image or regular replicas.
Never use `--locals` or profile an app holding real keys. The report records the exact
successful command or platform failure. See [report](../docs/benchmarks/load-test-report.md).
