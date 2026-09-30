from pathlib import Path

import pytest

from loadtest.ramp import summarize_ramp


def test_error_only_throughput_retains_generator_coverage_separately() -> None:
    stages = [
        {
            "offered_rps": 100,
            "throughput_rps": 99.5,
            "error_rate": 0,
            "overhead_ms": {"p99": 8},
            "measurement_complete": True,
            "dropped_iterations": 0,
        },
        {
            "offered_rps": 200,
            "throughput_rps": 160,
            "error_rate": 0.0005,
            "overhead_ms": {"p99": 100},
            "measurement_complete": True,
            "dropped_iterations": 2000,
        },
        {
            "offered_rps": 400,
            "throughput_rps": 180,
            "error_rate": 0.01,
            "overhead_ms": {"p99": 200},
            "measurement_complete": True,
            "dropped_iterations": 3000,
        },
    ]

    result = summarize_ramp(stages, 800)

    assert result["capacity"] == 100
    assert result["saturation_rate"] == 200
    assert result["saturation_throughput_rps"] == 160
    assert not result["saturation_generation_complete"]
    assert result["fully_generated_saturation_rate"] == 100
    assert result["fully_generated_saturation_throughput_rps"] == 99.5


def test_missing_telemetry_cannot_establish_throughput() -> None:
    result = summarize_ramp([{"measurement_complete": False, "offered_rps": 800}], 800)

    assert result["capacity"] == 0
    assert result["saturation_throughput_rps"] == 0


def test_slo_definition_keeps_generation_coverage_separate() -> None:
    result = summarize_ramp(
        [
            {
                "offered_rps": 100,
                "throughput_rps": 85,
                "error_rate": 0,
                "overhead_ms": {"p99": 8},
                "measurement_complete": True,
                "dropped_iterations": 2,
            }
        ],
        800,
    )

    assert result["capacity"] == 100
    assert not result["capacity_generation_complete"]
    assert not result["saturation_generation_complete"]


def test_ramp_continues_after_a_dropped_iteration_until_client_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from unittest.mock import Mock

    from loadtest.run import run_scenario

    (tmp_path / "provider.json").write_text(json.dumps({"median": {"client_ms": {"p99": 200}}}))
    stages = [
        {
            "offered_rps": rate,
            "throughput_rps": rate - 1,
            "error_rate": 0,
            "overhead_ms": {"p99": 30},
            "client_ms": {"p99": client},
            "measurement_complete": True,
            "dropped_iterations": dropped,
        }
        for rate, client, dropped in ((100, 210, 1), (200, 1200, 10))
    ]
    generator = Mock(side_effect=stages * 3)
    monkeypatch.setattr("loadtest.run.RESULTS", tmp_path)
    monkeypatch.setattr("loadtest.run.RATES", (100, 200, 400))
    monkeypatch.setattr("loadtest.run.run_once", generator)

    monkeypatch.setattr("loadtest.run.environment", Mock(return_value={}))

    result = run_scenario("S3")

    assert generator.call_count == 6
    assert all(ramp["stages"] == stages for ramp in result["runs"])
