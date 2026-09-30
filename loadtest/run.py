"""One command per scenario, preserving all three repetitions and failure evidence."""

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from loadtest.analysis import capacity_passes, median_run
from loadtest.execution import client_metrics, execute_k6, read_summary
from loadtest.measurements import (
    overhead,
    provider_stats,
    queue_series,
    snapshot,
    usage_counts,
)
from loadtest.rpm import rpm_observation
from loadtest.runtime import RESULTS, prepare_directories
from loadtest.setup import create_team, setup

RATES = (1, 5, 10, 20, 40, 80, 160, 320, 640, 1280)


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
    _warm_up(scenario, key_path, replicas)
    time.sleep(3)  # scrape boundary; no benchmark requests are issued during this wait
    before = snapshot(replicas, route) if org else {}
    upstream_before = provider_stats()
    usage_before = usage_counts(org) if org else {}
    start, end, samples = execute_k6(directory, scenario, rate, seconds, target, key_path)
    time.sleep(3)  # writer flush and final scrape; accounting is verified below, not assumed
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
        chosen = median_run(runs, scores=[float(run["capacity"]) for run in runs])
        result = {"scenario": scenario, "runs": runs, "median": chosen}
    else:
        rate = (
            50
            if scenario == "S6"
            else (5 if scenario in {"smoke", "provider", "S5"} else _dependent_rate(baseline_rate))
        )
        seconds = (
            600
            if scenario == "S7"
            else 180
            if scenario == "S6"
            else 30
            if scenario == "smoke"
            else 60
        )
        runs = [
            run_once(scenario, rate, seconds, replicas, repetition) for repetition in range(1, 4)
        ]
        chosen = median_run(runs, scores=[float(run["client_ms"]["p99"]) for run in runs])
        result = {"scenario": scenario, "runs": runs, "median": chosen}
    serialized = json.dumps(result, indent=2)
    history = RESULTS / "history"
    history.mkdir(exist_ok=True)
    (history / f"{scenario}-{uuid.uuid4().hex}.json").write_text(serialized)
    (RESULTS / f"{scenario}.json").write_text(serialized)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario", choices=["setup", "all", "provider", "smoke", *[f"S{i}" for i in range(1, 8)]]
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
        for scenario in ("provider", *[f"S{i}" for i in range(1, 8)]):
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
            if p99 is None or p99 >= 50 or run["error_rate"] or run["dropped_iterations"]:
                raise SystemExit(
                    "Smoke failed: missing/excessive overhead, errors or dropped iterations"
                )


def _ramp(scenario: str, replicas: int, repetition: int) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    capacity = 0
    for rate in RATES:
        stage = run_once(scenario, rate, 60, replicas, repetition)
        stages.append(stage)
        if not capacity_passes(
            stage["overhead_ms"]["p99"], stage["error_rate"], stage["dropped_iterations"]
        ):
            break
        capacity = rate
    return {"capacity": capacity, "stages": stages, "ceiling_reached": capacity == RATES[-1]}


def _dependent_rate(baseline_rate: int | None) -> int:
    if baseline_rate is None:
        path = RESULTS / "S1.json"
        if not path.exists():
            raise ValueError("Run S1 first; S2/S4/S5/S7 require its measured capacity")
        baseline_rate = int(json.loads(path.read_text())["median"]["capacity"])
    if baseline_rate <= 0:
        raise ValueError("S1 found no SLO-compliant capacity; cannot invent a 70% load")
    return max(1, int(baseline_rate * 0.7))


def _warm_up(scenario: str, key_path: Path | None, replicas: int) -> None:
    if key_path is None:
        return
    headers = {"authorization": f"Bearer {key_path.read_text().strip()}", "x-lgw-cache": "disabled"}
    with httpx.Client(timeout=15) as client:
        for port in (18001, 18002)[:replicas]:
            # Models warms auth without creating a provider receipt or spending limited-team RPM.
            if scenario != "S6":
                response = client.get(f"http://127.0.0.1:{port}/v1/models", headers=headers)
                response.raise_for_status()


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
    return {
        "scenario": scenario,
        "offered_rps": rate,
        "duration_s": seconds,
        "replicas": replicas,
        "start": start,
        "end": end,
        "artifact": directory.name,
        "overhead_ms": overhead(before, after) if org else {"p50": None, "p95": None, "p99": None},
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
        "container_samples": samples,
        "queue": queue_series(start, end, replicas) if org else [],
        "rpm": rpm_observation(org) if scenario == "S6" else None,
    }


if __name__ == "__main__":
    main()
