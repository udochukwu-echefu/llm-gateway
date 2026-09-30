"""Run k6 while sampling container resources; preserve generator failures for analysis."""

import threading
import time
from pathlib import Path
from typing import Any

from loadtest.measurements import container_sample
from loadtest.runtime import compose


def execute_k6(
    directory: Path, scenario: str, rate: int, seconds: int, target: str, key_path: Path | None
) -> tuple[float, float, list[dict[str, Any]]]:
    stop = threading.Event()
    samples: list[dict[str, Any]] = []
    sampler = threading.Thread(target=_sample_containers, args=(stop, samples), daemon=True)
    sampler.start()
    start = time.time()
    arguments = [
        "run",
        "--rm",
        "--no-deps",
        "-e",
        f"SCENARIO={scenario}",
        "-e",
        f"RATE={rate}",
        "-e",
        f"DURATION={seconds}s",
        "-e",
        f"TARGET={target}",
        "-e",
        f"OUTPUT={directory.name}",
    ]
    if key_path is not None:
        arguments.extend(["-e", f"KEY_FILE={key_path.name}"])
    try:
        compose(
            *arguments,
            "k6",
            "run",
            "--quiet",
            "--out",
            f"json=/results/{directory.name}/points.json",
            "/scripts/scenario.js",
            allow_failure=True,
        )
    finally:
        stop.set()
        sampler.join(timeout=30)
    if sampler.is_alive():
        raise RuntimeError("Container stats sampler did not stop")
    return start, time.time(), samples


def read_summary(directory: Path) -> dict[str, Any]:
    import json

    summary_path = directory / "summary.json"
    if not summary_path.exists():
        raise RuntimeError(f"k6 produced no summary: {directory.name}; run failed, not a pass")
    return json.loads(summary_path.read_text())["metrics"]


def client_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_ms": {
            f"p{p}": metrics["client_latency"]["values"][f"p({p})"] for p in (50, 95, 99)
        },
        "first_byte_ms": {
            f"p{p}": metrics["first_byte_latency"]["values"][f"p({p})"] for p in (50, 95, 99)
        },
        "successes": metrics.get("successful_requests", {}).get("values", {}).get("count", 0),
        "throughput_rps": metrics.get("successful_requests", {}).get("values", {}).get("rate", 0),
        "error_rate": metrics["unexpected_errors"]["values"]["rate"],
        "limited": metrics.get("limited_requests", {}).get("values", {}).get("count", 0),
        "dropped_iterations": metrics.get("dropped_iterations", {})
        .get("values", {})
        .get("count", 0),
        "cache_hit_ratio": metrics.get("cache_hits", {}).get("values", {}).get("rate"),
    }


def _sample_containers(stop: threading.Event, samples: list[dict[str, Any]]) -> None:
    while not stop.is_set():
        try:
            samples.append(container_sample())
        except (RuntimeError, ValueError):
            samples.append({"time": time.time(), "error": "container stats unavailable"})
        stop.wait(5)
