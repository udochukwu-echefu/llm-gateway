"""Classify observed throughput separately from delivering the full offered workload."""

from collections.abc import Sequence
from typing import Any

from loadtest.analysis import capacity_passes


def summarize_ramp(stages: Sequence[dict[str, Any]], ceiling: int) -> dict[str, Any]:
    measured = [stage for stage in stages if stage["measurement_complete"]]
    eligible = [stage for stage in measured if stage["error_rate"] < 0.001]
    generated = [stage for stage in eligible if stage["dropped_iterations"] == 0]
    slo = [
        stage
        for stage in measured
        if capacity_passes(stage["overhead_ms"]["p99"], stage["error_rate"], 0)
    ]
    observed = max(eligible, key=lambda stage: stage["offered_rps"], default=None)
    complete = max(generated, key=lambda stage: stage["offered_rps"], default=None)
    capacity = max(slo, key=lambda stage: stage["offered_rps"], default=None)
    return {
        "capacity": capacity["offered_rps"] if capacity else 0,
        "capacity_generation_complete": capacity["dropped_iterations"] == 0 if capacity else False,
        "saturation_rate": observed["offered_rps"] if observed else 0,
        "saturation_throughput_rps": observed["throughput_rps"] if observed else 0,
        "saturation_generation_complete": observed["dropped_iterations"] == 0
        if observed
        else False,
        "fully_generated_saturation_rate": complete["offered_rps"] if complete else 0,
        "fully_generated_saturation_throughput_rps": complete["throughput_rps"] if complete else 0,
        "stages": list(stages),
        "ceiling_reached": bool(stages) and stages[-1]["offered_rps"] == ceiling,
    }
