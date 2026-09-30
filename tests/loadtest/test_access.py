import pytest

from loadtest.access import access_rows, cache_breakdown, percentiles
from loadtest.rpm import inspect_times


def test_access_uses_run_id_and_ignores_other_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    def logs(*args: str) -> str:
        return "\n".join(
            [
                '{"event":"request","request_id":"run-request-1","overhead_ms":1.234567,"key_cache":"hit"}',
                '{"event":"request","request_id":"run-warmup-request-1","overhead_ms":99}',
                "other",
            ]
        )

    monkeypatch.setattr("loadtest.access.compose", logs)

    rows = access_rows("run", 0, 1)

    assert len(rows) == 1
    assert rows[0]["overhead_ms"] == 1.234567
    assert cache_breakdown(rows)["hit"]["count"] == 1
    assert cache_breakdown(rows)["miss"]["p99"] is None


def test_exact_percentiles_interpolate_actual_observations() -> None:
    assert percentiles([1, 2, 3, 4])["p99"] == pytest.approx(3.97)
    assert percentiles([])["p99"] is None


def test_rolling_bound_includes_burst() -> None:
    assert inspect_times([0.0] * 630, 600, burst=30)["exact_rolling_no_over_admission"]
    assert not inspect_times([0.0] * 631, 600, burst=30)["exact_rolling_no_over_admission"]
