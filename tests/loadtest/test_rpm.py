from loadtest.rpm import inspect_times


def test_fixed_buckets_can_pass_while_exact_rolling_window_over_admits() -> None:
    result = inspect_times([59.0] * 600 + [119.0] * 599, 600)

    assert result["fixed_bucket_no_over_admission"] is True
    # Exactly 60 seconds old is excluded: boundary behavior is intentional.
    assert result["exact_rolling_no_over_admission"] is True
    overlap = inspect_times([59.1] * 600 + [119.0] * 599, 600)
    assert overlap["rolling_60s_max"] == 1199
    assert overlap["exact_rolling_no_over_admission"] is False


def test_missing_admissions_are_not_an_exactness_pass() -> None:
    assert inspect_times([], 600)["exact_rolling_no_over_admission"] is False
