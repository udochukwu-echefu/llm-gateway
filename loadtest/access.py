"""Extract only benchmark access metadata; never persist credentials or payloads."""

import json
import math
from collections.abc import Sequence
from typing import Any

from loadtest.runtime import REPLICAS, compose


def access_rows(artifact: str, start: float, replicas: int) -> list[dict[str, Any]]:
    output = compose("logs", "--no-log-prefix", "--since", str(int(start)), *REPLICAS[:replicas])
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") == "request" and row.get("request_id", "").startswith(
            artifact + "-request-"
        ):
            rows.append(
                {
                    name: row.get(name)
                    for name in (
                        "request_id",
                        "overhead_ms",
                        "key_cache",
                        "status",
                        "rpm_admitted_at_us",
                    )
                }
            )
    return rows


def percentiles(values: Sequence[float]) -> dict[str, float | None]:
    """Linear interpolation of sorted exact observations (same convention as k6)."""
    ordered = sorted(values)
    if not ordered:
        return {f"p{p}": None for p in (50, 95, 99)}
    result: dict[str, float | None] = {}
    for p in (50, 95, 99):
        rank = (len(ordered) - 1) * p / 100
        left = math.floor(rank)
        result[f"p{p}"] = ordered[left] + (ordered[math.ceil(rank)] - ordered[left]) * (rank - left)
    return result


def cache_breakdown(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        kind: {"count": len(values), **percentiles(values)}
        for kind in ("hit", "miss")
        for values in [[float(row["overhead_ms"]) for row in rows if row["key_cache"] == kind]]
    }
