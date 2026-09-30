"""Inspect durable admission times without conflating fixed buckets and rolling minutes."""

import json
from collections import Counter
from collections.abc import Sequence

from loadtest.runtime import compose


def rpm_observation(org: str) -> dict[str, object]:
    if not org.startswith("loadtest-") or not all(c.isalnum() or c == "-" for c in org):
        raise ValueError("Only generated benchmark organization names are accepted")
    sql = f"""SELECT coalesce(json_agg(extract(epoch FROM u.created_at)
        ORDER BY u.created_at), '[]'::json) FROM usage_records u
        JOIN organizations o ON o.id = u.organization_id
        WHERE o.name = '{org}' AND u.outcome = 'success'"""  # noqa: S608 -- generated names exclude SQL syntax
    output = compose(
        "exec", "-T", "postgres", "psql", "-U", "gateway", "-d", "gateway_loadtest", "-Atc", sql
    )
    return inspect_times(json.loads(output), 600)


def inspect_times(times: Sequence[float], limit: int, *, burst: int = 0) -> dict[str, object]:
    ordered = sorted(times)
    buckets = Counter(int(timestamp // 60) for timestamp in ordered)
    left = maximum = 0
    for right, timestamp in enumerate(ordered):
        while ordered[left] <= timestamp - 60:
            left += 1
        maximum = max(maximum, right - left + 1)
    return {
        "fixed_minute_counts": dict(sorted(buckets.items())),
        "fixed_minute_max": max(buckets.values(), default=0),
        "rolling_60s_max": maximum,
        "fixed_bucket_no_over_admission": bool(times) and max(buckets.values()) <= limit,
        "exact_rolling_no_over_admission": bool(times) and maximum <= limit + burst,
        "burst": burst,
        "rolling_bound": limit + burst,
        "timestamp_basis": "receipt request-start time, not an atomic Redis admission timestamp",
    }
