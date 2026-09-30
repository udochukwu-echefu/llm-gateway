from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from loadtest.run import run_scenario


def test_three_runs_use_seventy_percent_of_measured_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    run = Mock(side_effect=[{"client_ms": {"p99": value}} for value in (3, 1, 2)])
    monkeypatch.setattr("loadtest.run.run_once", run)

    result = run_scenario("S2", baseline_rate=10)

    assert len(result["runs"]) == 3
    assert result["median"]["client_ms"]["p99"] == 2
    assert [call.args for call in run.call_args_list] == [
        ("S2", 7, 60, 1, repetition) for repetition in range(1, 4)
    ]
    assert len(list((tmp_path / "history").glob("*.json"))) == 1


def test_zero_capacity_cannot_become_an_invented_baseline() -> None:
    with pytest.raises(ValueError, match="no SLO-compliant capacity"):
        run_scenario("S7", baseline_rate=0)


def test_ramp_stops_on_first_missed_target_and_keeps_failed_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    monkeypatch.setattr("loadtest.run.RATES", (5, 10, 20))

    def stage(
        scenario: str, rate: int, seconds: int, replicas: int, repetition: int
    ) -> dict[str, Any]:
        return {
            "overhead_ms": {"p99": 5 if rate == 5 else 12},
            "error_rate": 0,
            "dropped_iterations": 0,
        }

    run = Mock(side_effect=stage)
    monkeypatch.setattr("loadtest.run.run_once", run)

    result = run_scenario("S3")

    assert result["median"]["capacity"] == 5
    assert len(result["median"]["stages"]) == 2
    assert run.call_count == 6
    assert all(call.args[3] == 2 for call in run.call_args_list)


def test_embedding_cache_scenario_does_not_require_passing_s1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    run = Mock(return_value={"client_ms": {"p99": 1}})
    monkeypatch.setattr("loadtest.run.run_once", run)

    run_scenario("S5")

    assert all(call.args[1] == 5 for call in run.call_args_list)
