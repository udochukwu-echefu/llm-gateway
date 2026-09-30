import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from loadtest.run import run_scenario


@pytest.mark.parametrize(("capacity", "rate"), [(100, 50), (0, 50), (50, 25)])
def test_dependent_scenario_runs_once_with_declared_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capacity: int, rate: int
) -> None:
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    run = Mock(return_value={"client_ms": {"p99": 1}})
    monkeypatch.setattr("loadtest.run.run_once", run)

    result = run_scenario("S2", baseline_rate=capacity)

    assert run.call_args.args == ("S2", rate, 60, 1, 1)
    assert len(result["runs"]) == 1
    assert ("fallback" in result["rate_rule"]) == (capacity == 0)


def test_ramp_continues_after_slo_miss_and_stops_at_saturation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    monkeypatch.setattr("loadtest.run.RATES", (10, 25, 50, 100))
    (tmp_path / "provider.json").write_text(json.dumps({"median": {"client_ms": {"p99": 200}}}))

    def stage(
        scenario: str, rate: int, seconds: int, replicas: int, repetition: int
    ) -> dict[str, object]:
        return {
            "offered_rps": rate,
            "overhead_ms": {"p99": 5 if rate == 10 else 12},
            "client_ms": {"p99": 1100 if rate == 50 else 220},
            "error_rate": 0,
            "dropped_iterations": 0,
            "measurement_complete": True,
            "throughput_rps": rate - 0.1,
        }

    run = Mock(side_effect=stage)
    monkeypatch.setattr("loadtest.run.run_once", run)

    result = run_scenario("S3")

    assert result["median"]["capacity"] == 10
    assert result["median"]["saturation_rate"] == 50
    assert len(result["median"]["stages"]) == 3
    assert run.call_count == 9
    assert [call.args[2] for call in run.call_args_list[:3]] == [300, 120, 60]
