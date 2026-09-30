"""Render k6 point output with an ephemeral matplotlib install, not a project dependency."""

import json
from collections import defaultdict
from datetime import datetime
from importlib import import_module
from pathlib import Path

from loadtest.runtime import RESULTS, ROOT


def render() -> None:
    # Optional visualization dependency only; the core runner never imports it.
    plt = import_module("matplotlib.pyplot")

    output = ROOT / "docs" / "benchmarks"
    output.mkdir(parents=True, exist_ok=True)
    for scenario in range(1, 8):
        summary_path = RESULTS / f"S{scenario}.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text())
        if summary.get("status") == "BLOCKED":
            continue
        chosen = summary["median"]
        runs = chosen.get("stages", [chosen])
        figure, axes = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True)
        for run in runs:
            latency, successes = read_points(RESULTS / run["artifact"] / "points.json")
            label = f"offered {run['offered_rps']}/s"
            axes[0].scatter(
                [x for x, _ in latency], [y for _, y in latency], alpha=0.55, s=4, label=label
            )
            axes[1].plot([x for x, _ in successes], [y for _, y in successes], label=label)
        axes[0].set(ylabel="Client duration (ms)", title=f"S{scenario}: median run, k6 points")
        axes[1].set(
            xlabel="Seconds since first response point", ylabel="Successful requests / 1 s bin"
        )
        axes[0].legend()
        axes[1].legend()
        figure.savefig(output / f"S{scenario}.png", dpi=140)
        plt.close(figure)


def read_points(path: Path) -> tuple[list[tuple[float, float]], list[tuple[float, int]]]:
    points: list[tuple[str, float, float]] = []
    successes: dict[int, int] = defaultdict(int)
    with path.open() as input_file:
        for line in input_file:
            row = json.loads(line)
            if row["type"] != "Point" or row["metric"] not in {
                "client_latency",
                "successful_requests",
            }:
                continue
            timestamp = datetime.fromisoformat(row["data"]["time"]).timestamp()
            points.append((row["metric"], timestamp, float(row["data"]["value"])))
    if not points:
        return [], []
    start = min(timestamp for _, timestamp, _ in points)
    latency = sorted(
        (timestamp - start, value)
        for metric, timestamp, value in points
        if metric == "client_latency"
    )
    for metric, timestamp, value in points:
        if metric == "successful_requests":
            successes[int(timestamp - start)] += int(value)
    end = int(max(timestamp for _, timestamp, _ in points) - start)
    return latency, [(second, successes[second]) for second in range(end + 1)]


if __name__ == "__main__":
    render()
