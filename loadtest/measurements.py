"""Metadata-only snapshots from Prometheus, Docker and the isolated benchmark database."""

import json
import math
import time
from typing import Any

import httpx

from loadtest.analysis import histogram_quantile
from loadtest.runtime import REPLICAS, compose

PROMETHEUS = "http://127.0.0.1:9090"


def query(expression: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=15) as client:
        response = client.get(f"{PROMETHEUS}/api/v1/query", params={"query": expression})
        response.raise_for_status()
        value = response.json()
    if value["status"] != "success":
        raise RuntimeError("Prometheus query failed")
    return value["data"]["result"]


def snapshot(replicas: int, route: str) -> dict[str, float]:
    selected = "|".join(f"{name}:9464" for name in REPLICAS[:replicas])
    labels = f'job="loadtest",instance=~"{selected}"'
    values: dict[str, float] = {}
    buckets = query(
        f'sum by (le) (lgw_gateway_overhead_seconds_bucket{{{labels},route="{route}"}})'
    )
    for row in buckets:
        values[f"bucket:{row['metric']['le']}"] = float(row["value"][1])
    for metric in (
        "lgw_usage_records_dropped_total",
        "lgw_usage_records_lost_total",
        "lgw_upstream_requests_total",
        "lgw_redis_errors_total",
    ):
        rows = query(f"sum({metric}{{{labels}}})")
        values[metric] = float(rows[0]["value"][1]) if rows else 0
    return values


def overhead(before: dict[str, float], after: dict[str, float]) -> dict[str, float | None]:
    buckets = {
        float(key[7:]): value - before.get(key, 0)
        for key, value in after.items()
        if key.startswith("bucket:")
    }
    if any(value < 0 for value in buckets.values()):
        raise ValueError("Counter reset during benchmark")
    return {
        f"p{percentile}": _milliseconds(histogram_quantile(buckets, percentile / 100))
        for percentile in (50, 95, 99)
    }


def container_sample() -> dict[str, Any]:
    output = compose(
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        "fake-provider",
        *REPLICAS,
        "loadtest-nginx",
        "prometheus",
    )
    return {"time": time.time(), "containers": [json.loads(line) for line in output.splitlines()]}


def provider_stats() -> dict[str, int]:
    with httpx.Client(timeout=10) as client:
        response = client.get("http://127.0.0.1:18000/stats")
        response.raise_for_status()
        return response.json()


def usage_counts(org: str) -> dict[str, int]:
    if not org.startswith("loadtest-") or not all(
        character.isalnum() or character == "-" for character in org
    ):
        raise ValueError("Only generated benchmark organization names are accepted")
    sql = f"""SELECT json_build_object(
        'records', count(*),
        'provider_success', count(*) FILTER (WHERE u.outcome = 'success'),
        'cache_hits', count(*) FILTER (WHERE u.outcome = 'cache_hit'),
        'errors', count(*) FILTER (WHERE u.outcome NOT IN ('success', 'cache_hit')))
        FROM usage_records u JOIN organizations o ON u.organization_id = o.id
        WHERE o.name = '{org}'"""  # noqa: S608 -- generated name validated above; quotes forbidden
    result = compose(
        "exec", "-T", "postgres", "psql", "-U", "gateway", "-d", "gateway_loadtest", "-Atc", sql
    )
    return json.loads(result)


def queue_series(start: float, end: float, replicas: int) -> list[dict[str, Any]]:
    selected = "|".join(f"{name}:9464" for name in REPLICAS[:replicas])
    expression = f'sum(lgw_usage_queue_depth{{job="loadtest",instance=~"{selected}"}})'
    with httpx.Client(timeout=15) as client:
        response = client.get(
            f"{PROMETHEUS}/api/v1/query_range",
            params={
                "query": expression,
                "start": start,
                "end": end,
                "step": 2,
            },
        )
        response.raise_for_status()
        return response.json()["data"]["result"]


def _milliseconds(value: float | None) -> float | None:
    return value * 1000 if value is not None and math.isfinite(value) else None
