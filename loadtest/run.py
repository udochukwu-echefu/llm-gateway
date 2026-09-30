"""One command per scenario, preserving all three repetitions and failure evidence."""

import argparse
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

from loadtest.access import access_rows, cache_breakdown, percentiles
from loadtest.analysis import capacity_passes, measurement_coverage, median_run
from loadtest.environment import environment
from loadtest.execution import client_metrics, execute_k6, read_summary
from loadtest.measurements import (
    overhead,
    provider_stats,
    queue_series,
    snapshot,
    usage_counts,
)
from loadtest.rpm import inspect_times
from loadtest.runtime import RESULTS, prepare_directories
from loadtest.setup import create_team, setup

RATES = (10, 25, 50, 100, 200, 400, 800)


def run_once(
    scenario: str, rate: int, seconds: int, replicas: int, repetition: int
) -> dict[str, Any]:
    directory = RESULTS / f"{scenario}-{repetition}-{rate}-{uuid.uuid4().hex[:8]}"
    directory.mkdir()
    org, key_path = (
        create_team(scenario, 600 if scenario == "S6" else 0)
        if scenario != "provider"
        else ("", None)
    )
    route = "/v1/embeddings" if scenario == "S5" else "/v1/chat/completions"
    target = (
        "http://fake-provider:8000"
        if scenario == "provider"
        else ("http://loadtest-nginx:8000" if replicas == 2 else "http://gateway-loadtest-1:8000")
    )
    print(
        f"{scenario} repetition {repetition}: warmup 30s, then {seconds}s at {rate}/s", flush=True
    )
    warm_directory = RESULTS / f"{directory.name}-warmup"
    warm_directory.mkdir()
    warm_start, _, _ = execute_k6(warm_directory, scenario, rate, 30, target, key_path)
    time.sleep(3)  # scrape boundary; no benchmark requests are issued during this wait
    before = snapshot(replicas, route) if org else {}
    upstream_before = provider_stats()
    usage_before = usage_counts(org) if org else {}
    start, end, samples = execute_k6(directory, scenario, rate, seconds, target, key_path)
    time.sleep(3)  # writer flush and final scrape; accounting is verified below, not assumed
    warm_metrics = read_summary(warm_directory)
    result = _collect(
        directory,
        scenario,
        rate,
        seconds,
        replicas,
        start,
        end,
        before,
        upstream_before,
        usage_before,
        org,
        route,
        samples,
    )
    result["warmup"] = {
        "duration_s": 30,
        "artifact": warm_directory.name,
        **client_metrics(warm_metrics),
    }
    if scenario == "S6":
        warm_rows = access_rows(warm_directory.name, warm_start, replicas)
        times = [
            row["rpm_admitted_at_us"] / 1000000
            for row in [*warm_rows, *result["access"]]
            if row["rpm_admitted_at_us"] is not None
        ]
        result["rpm"] = inspect_times(times, 600, burst=30)
        result["rpm"]["timestamp_basis"] = "atomic Redis TIME at admission; warmup plus measurement"
        result["rpm"]["admissions"] = len(times)
        result["rpm"]["observations_complete"] = (
            len(times) == result["warmup"]["successes"] + result["successes"]
        )
        result["rpm"]["assertion_passed"] = (
            result["rpm"]["exact_rolling_no_over_admission"]
            and result["rpm"]["observations_complete"]
        )
    (directory / "measurement.json").write_text(json.dumps(result, indent=2))
    print(
        f"{scenario} repetition {repetition}, offered {rate}/s: "
        f"overhead p99={result['overhead_ms']['p99']}, errors={result['error_rate']}, "
        f"dropped iterations={result['dropped_iterations']}",
        flush=True,
    )
    return result


def run_scenario(scenario: str, *, baseline_rate: int | None = None) -> dict[str, Any]:
    replicas = 2 if scenario in {"S3", "S6", "S7"} else 1
    if scenario in {"S1", "S3"}:
        runs = [_ramp(scenario, replicas, repetition) for repetition in range(1, 4)]
        chosen = median_run(runs, scores=[float(run["saturation_throughput_rps"]) for run in runs])
        result = {"scenario": scenario, "runs": runs, "median": chosen}
    else:
        rate = (
            1
            if scenario == "idle"
            else 50
            if scenario == "S6"
            else (5 if scenario in {"smoke", "provider", "S5"} else _dependent_rate(baseline_rate))
        )
        seconds = (
            300
            if scenario == "idle"
            else 600
            if scenario == "S7"
            else 180
            if scenario == "S6"
            else 30
            if scenario == "smoke"
            else 60
        )
        repetitions = 3 if scenario in {"S6", "S5"} else 1
        runs = [
            run_once(scenario, rate, seconds, replicas, repetition)
            for repetition in range(1, repetitions + 1)
        ]
        chosen = (
            median_run(runs, scores=[float(run["client_ms"]["p99"]) for run in runs])
            if repetitions == 3
            else runs[0]
        )
        result = {"scenario": scenario, "runs": runs, "median": chosen}
    if scenario in {"S2", "S4", "S7"}:
        result["rate_rule"] = (
            "50% of S1 SLO capacity"
            if _s1_capacity(baseline_rate) > 0
            else "fallback 50 req/s: no S1 SLO capacity"
        )
    result["environment"] = environment()
    serialized = json.dumps(result, indent=2)
    history = RESULTS / "history"
    history.mkdir(exist_ok=True)
    (history / f"{scenario}-{uuid.uuid4().hex}.json").write_text(serialized)
    (RESULTS / f"{scenario}.json").write_text(serialized)
    if scenario == "S6" and any(not run["rpm"]["assertion_passed"] for run in runs):
        raise RuntimeError(
            "S6 rolling-60s admission bound or observation coverage failed; evidence retained"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario",
        choices=["setup", "all", "provider", "smoke", "idle", *[f"S{i}" for i in range(1, 8)]],
    )
    parser.add_argument("--skip-setup", action="store_true")
    args = parser.parse_args()
    prepare_directories()
    if not args.skip_setup:
        setup()
    if args.scenario == "setup":
        return
    if args.scenario == "all":
        blocked: list[str] = []
        for scenario in ("provider", *[f"S{i}" for i in range(1, 8)], "idle"):
            try:
                run_scenario(scenario)
            except ValueError as error:
                blocked.append(scenario)
                (RESULTS / f"{scenario}.json").write_text(
                    json.dumps(
                        {
                            "scenario": scenario,
                            "status": "BLOCKED",
                            "reason": str(error),
                            "runs": [],
                        },
                        indent=2,
                    )
                )
                print(f"{scenario} BLOCKED: {error}", flush=True)
        if blocked:
            raise SystemExit(f"Incomplete benchmarks; blocked scenarios: {', '.join(blocked)}")
        return
    result = run_scenario(args.scenario)
    if args.scenario == "smoke":
        for run in result["runs"]:
            p99 = run["overhead_ms"]["p99"]
            if (
                p99 is None
                or p99 >= 50
                or run["error_rate"]
                or run["dropped_iterations"]
                or not run["measurement_complete"]
            ):
                raise SystemExit(
                    "Smoke failed: missing/excessive overhead, errors or dropped iterations"
                )


def _ramp(scenario: str, replicas: int, repetition: int) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    capacity = saturation_rate = 0
    throughput = 0.0
    baseline = json.loads((RESULTS / "provider.json").read_text())["median"]["client_ms"]["p99"]
    for rate in RATES:
        stage = run_once(scenario, rate, max(60, math.ceil(3000 / rate)), replicas, repetition)
        stages.append(stage)
        complete = stage["measurement_complete"] and stage["dropped_iterations"] == 0
        if complete and capacity_passes(stage["overhead_ms"]["p99"], stage["error_rate"], 0):
            capacity = rate
        if complete and stage["error_rate"] < 0.001:
            saturation_rate, throughput = rate, stage["throughput_rps"]
        if not complete or stage["error_rate"] > 0.01 or stage["client_ms"]["p99"] > 5 * baseline:
            break
    return {
        "capacity": capacity,
        "saturation_rate": saturation_rate,
        "saturation_throughput_rps": throughput,
        "stages": stages,
        "ceiling_reached": stages[-1]["offered_rps"] == RATES[-1],
    }


def _s1_capacity(baseline_rate: int | None) -> int:
    if baseline_rate is not None:
        return baseline_rate
    path = RESULTS / "S1.json"
    if not path.exists():
        raise ValueError("Run S1 first to select the dependent scenario rate")
    return int(json.loads(path.read_text())["median"]["capacity"])


def _dependent_rate(baseline_rate: int | None) -> int:
    capacity = _s1_capacity(baseline_rate)
    return max(1, int(capacity * 0.5)) if capacity > 0 else 50


def _collect(
    directory: Path,
    scenario: str,
    rate: int,
    seconds: int,
    replicas: int,
    start: float,
    end: float,
    before: dict[str, float],
    upstream_before: dict[str, int],
    usage_before: dict[str, int],
    org: str,
    route: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = read_summary(directory)
    after = snapshot(replicas, route) if org else {}
    upstream_after = provider_stats()
    usage_after = usage_counts(org) if org else {}
    rows = access_rows(directory.name, start, replicas) if org else []
    exact = percentiles([float(row["overhead_ms"]) for row in rows])
    return {
        "scenario": scenario,
        "offered_rps": rate,
        "duration_s": seconds,
        "replicas": replicas,
        "start": start,
        "end": end,
        "artifact": directory.name,
        "overhead_ms": exact,
        "histogram_overhead_ms": overhead(before, after) if org else exact,
        "access": rows,
        "key_cache": cache_breakdown(rows),
        **client_metrics(metrics),
        "provider_delta": {
            key: upstream_after[key] - value for key, value in upstream_before.items()
        },
        "usage_delta": {key: usage_after[key] - value for key, value in usage_before.items()},
        "metric_delta": {
            key: value - before.get(key, 0)
            for key, value in after.items()
            if not key.startswith("bucket:")
        },
        "histogram_delta": {
            key[7:]: value - before.get(key, 0)
            for key, value in after.items()
            if key.startswith("bucket:")
        },
        "measurement_complete": not org
        or (
            measurement_coverage(
                len(rows), metrics.get("http_reqs", {}).get("values", {}).get("count")
            )
            and measurement_coverage(
                after.get("bucket:+Inf", 0) - before.get("bucket:+Inf", 0),
                metrics.get("http_reqs", {}).get("values", {}).get("count"),
            )
        ),
        "container_samples": samples,
        "queue": queue_series(start, end, replicas) if org else [],
        "rpm": None,
    }


if __name__ == "__main__":
    main()
