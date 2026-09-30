import math

import pytest

from loadtest.analysis import capacity_passes, histogram_quantile, median_run, memory_slope
from loadtest.measurements import overhead


def test_histogram_quantile_uses_bucket_delta_not_average() -> None:
    buckets = {0.001: 50, 0.01: 99, 0.05: 100, math.inf: 100}

    assert histogram_quantile(buckets, 0.5) == 0.001
    assert histogram_quantile(buckets, 0.99) == pytest.approx(0.01)


def test_empty_histogram_is_missing_not_zero() -> None:
    assert histogram_quantile({}, 0.99) is None
    assert not capacity_passes(None, 0, 0)


def test_counter_reset_is_rejected() -> None:
    with pytest.raises(ValueError, match="Counter reset"):
        overhead({"bucket:+Inf": 10}, {"bucket:+Inf": 1})


def test_capacity_checks_exact_slo_boundaries() -> None:
    assert capacity_passes(9.99, 0.001, 0)
    assert not capacity_passes(10, 0, 0)
    assert not capacity_passes(1, 0.0011, 0)
    assert not capacity_passes(1, 0, 1)


def test_median_selects_one_complete_run() -> None:
    assert median_run(["first", "second", "third"], scores=[3, 1, 2]) == "third"
    with pytest.raises(ValueError, match="Exactly three"):
        median_run(["one"], scores=[1])


def test_memory_regression_preserves_positive_and_negative_trends() -> None:
    assert memory_slope([(0, 10), (1, 12), (2, 14)]) == 2
    assert memory_slope([(0, 10), (1, 8), (2, 6)]) == -2
    assert memory_slope([]) is None
