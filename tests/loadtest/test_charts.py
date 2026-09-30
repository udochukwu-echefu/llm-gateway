import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from loadtest.charts import read_points, render


def test_charts_read_only_named_metric_points(tmp_path: Path) -> None:
    path = tmp_path / "points.json"
    rows = [
        {"type": "Metric", "metric": "client_latency"},
        {
            "type": "Point",
            "metric": "client_latency",
            "data": {"time": "2026-09-30T00:00:00Z", "value": 200},
        },
        {
            "type": "Point",
            "metric": "successful_requests",
            "data": {"time": "2026-09-30T00:00:00Z", "value": 1},
        },
        {
            "type": "Point",
            "metric": "client_latency",
            "data": {"time": "2026-09-30T00:00:01Z", "value": 205},
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows))

    latency, successes = read_points(path)

    assert latency == [(0, 200), (1, 205)]
    assert successes == [(0, 1), (1, 0)]


def test_blocked_scenarios_do_not_get_invented_charts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "S1.json").write_text(json.dumps({"status": "BLOCKED"}))
    plots = Mock()
    monkeypatch.setattr("loadtest.charts.RESULTS", tmp_path)
    monkeypatch.setattr("loadtest.charts.ROOT", tmp_path)
    monkeypatch.setattr("loadtest.charts.import_module", Mock(return_value=plots))

    render()

    plots.subplots.assert_not_called()


def test_chart_fills_zero_admissions_and_sorts_out_of_order_points(tmp_path: Path) -> None:
    path = tmp_path / "points.json"
    rows = [
        {
            "type": "Point",
            "metric": "client_latency",
            "data": {"time": "2026-09-30T00:00:02Z", "value": 200},
        },
        {
            "type": "Point",
            "metric": "successful_requests",
            "data": {"time": "2026-09-30T00:00:00Z", "value": 1},
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows))

    latency, successes = read_points(path)

    assert latency == [(2, 200)]
    assert successes == [(0, 1), (1, 0), (2, 0)]
