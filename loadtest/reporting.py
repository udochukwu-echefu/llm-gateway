"""Metadata summaries for the report; unavailable resource samples remain unavailable."""

import re
from collections import defaultdict
from typing import Any

from loadtest.analysis import memory_slope

FACTORS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
}


def memory_bytes(value: str) -> float:
    match = re.fullmatch(r"([0-9.]+)([A-Za-z]+)", value.strip())
    if match is None or match[2] not in FACTORS:
        raise ValueError("Unknown Docker memory unit")
    return float(match[1]) * FACTORS[match[2]]


def resource_summary(run: dict[str, Any]) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for sample in run["container_samples"]:
        for container in sample.get("containers", []):
            memory = memory_bytes(container["MemUsage"].split("/")[0])
            cpu = float(container["CPUPerc"].rstrip("%"))
            groups[container["Name"]].append((sample["time"], cpu, memory))
    return {
        name: _summarize(values, run["start"], run["scenario"] == "S7")
        for name, values in sorted(groups.items())
    }


def queue_maximum(run: dict[str, Any]) -> float | None:
    values = [float(value) for series in run["queue"] for _, value in series["values"]]
    return max(values) if values else None


def _summarize(
    values: list[tuple[float, float, float]],
    start: float,
    soak: bool,
) -> dict[str, float | int | None]:
    memory = [
        (timestamp, memory)
        for timestamp, _, memory in values
        if not soak or timestamp >= start + 120
    ]
    return {
        "samples": len(values),
        "cpu_mean_percent": sum(cpu for _, cpu, _ in values) / len(values),
        "cpu_peak_percent": max(cpu for _, cpu, _ in values),
        "memory_min_mib": min(memory for _, _, memory in values) / 1024**2,
        "memory_max_mib": max(memory for _, _, memory in values) / 1024**2,
        "memory_slope_bytes_per_second": memory_slope(memory),
    }
