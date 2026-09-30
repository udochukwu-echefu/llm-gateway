import json
from pathlib import Path

import pytest

from loadtest.execution import client_metrics, read_summary


def test_missing_k6_summary_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no summary"):
        read_summary(tmp_path)


def test_malformed_k6_summary_is_not_a_success(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text("not json")

    with pytest.raises(json.JSONDecodeError):
        read_summary(tmp_path)


def test_client_metrics_keep_expected_limits_separate_from_errors() -> None:
    quantiles = {"p(50)": 1, "p(95)": 2, "p(99)": 3}
    metrics = {
        "client_latency": {"values": quantiles},
        "first_byte_latency": {"values": quantiles},
        "successful_requests": {"values": {"count": 600, "rate": 10}},
        "limited_requests": {"values": {"count": 2400}},
        "unexpected_errors": {"values": {"rate": 0}},
        "dropped_iterations": {"values": {"count": 12}},
    }

    result = client_metrics(metrics)

    assert result["successes"] == 600
    assert result["limited"] == 2400
    assert result["error_rate"] == 0
    assert result["dropped_iterations"] == 12


def test_missing_latency_cannot_turn_into_zero() -> None:
    with pytest.raises(KeyError):
        client_metrics({})
