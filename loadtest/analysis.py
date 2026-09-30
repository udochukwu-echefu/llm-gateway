"""Pure benchmark arithmetic; absent measurements are never treated as zero latency."""

import math
from collections.abc import Mapping, Sequence


def histogram_quantile(buckets: Mapping[float, float], quantile: float) -> float | None:
    """Interpolate cumulative bucket deltas the same way as classic Prometheus histograms."""
    total = buckets.get(math.inf, 0)
    if total <= 0:
        return None
    rank = quantile * total
    previous_bound = previous_count = 0.0
    for bound, count in sorted(buckets.items()):
        if count < previous_count:
            raise ValueError("Histogram buckets must be cumulative")
        if count >= rank:
            if math.isinf(bound):
                return previous_bound
            if count == previous_count:
                return bound
            return previous_bound + (bound - previous_bound) * (
                (rank - previous_count) / (count - previous_count)
            )
        previous_bound, previous_count = bound, count
    raise ValueError("Histogram is missing its infinite bucket")


def capacity_passes(overhead_p99_ms: float | None, error_rate: float, dropped: int) -> bool:
    return (
        overhead_p99_ms is not None
        and overhead_p99_ms < 10
        and error_rate <= 0.001
        and dropped == 0
    )


def median_run[T](runs: Sequence[T], *, scores: Sequence[float]) -> T:
    if len(runs) != 3 or len(scores) != 3:
        raise ValueError("Exactly three runs are required")
    return sorted(zip(scores, range(3), runs, strict=True), key=lambda row: (row[0], row[1]))[1][2]


def memory_slope(samples: Sequence[tuple[float, float]]) -> float | None:
    """Least-squares bytes/second; warmup filtering belongs to the caller."""
    if len(samples) < 2:
        return None
    x_mean = sum(x for x, _ in samples) / len(samples)
    y_mean = sum(y for _, y in samples) / len(samples)
    denominator = sum((x - x_mean) ** 2 for x, _ in samples)
    if denominator == 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in samples) / denominator
