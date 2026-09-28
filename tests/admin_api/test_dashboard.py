"""The provisioned usage view keeps every required cost signal visible."""

import json
from pathlib import Path


def test_usage_dashboard_has_org_selector_and_all_required_panels() -> None:
    path = Path(__file__).resolve().parents[2] / "observability/grafana/dashboards/usage.json"
    dashboard = json.loads(path.read_text())
    titles = {panel["title"] for panel in dashboard["panels"]}
    queries = " ".join(
        target["rawSql"] for panel in dashboard["panels"] for target in panel["targets"]
    )

    assert dashboard["templating"]["list"][0]["name"] == "org"
    assert len(titles) == 5
    assert "Team spend this month vs budget (USD)" in titles
    assert "Top models by cost" in titles
    assert "Requests and tokens over time" in titles
    assert "Cache hit ratio and estimated savings" in titles
    assert "Unpriced usage (never counted as free)" in titles
    assert "usage_missing" in queries
    assert "stream_incomplete" in queries
    assert "api_keys" not in queries
    assert "admin_keys" not in queries
