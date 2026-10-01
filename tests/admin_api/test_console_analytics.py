"""SQL tail percentiles, unknown gaps and strict grouping validation."""

import pytest

from tests.admin_api.conftest import AdminHarness
from tests.admin_api.usage_fixtures import add_receipts

pytestmark = pytest.mark.db


async def test_analytics_percentiles_and_unknown_ttfb(admin_harness: AdminHarness) -> None:
    h = admin_harness
    await add_receipts(h)
    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/analytics?group_by=provider", headers=h.headers(h.org_key)
    )
    assert response.status_code == 200
    rows = {row["group"]: row for row in response.json()["data"]}
    assert rows["groq"]["requests"] == 2
    assert float(rows["groq"]["error_rate"]) == 1
    assert rows["groq"]["duration_p50"] == 150
    assert rows["groq"]["duration_p95"] == 195
    assert rows["groq"]["ttfb_p95"] is None
    assert rows["deepseek"]["fallback_count"] == 1
    assert rows["groq"]["retry_count"] == 1
    assert rows["groq"]["saved_usd"] is None
    assert rows["groq"]["redaction_count"] == 4


@pytest.mark.parametrize(
    "query",
    [
        "unknown=x",
        "group_by=key",
        "bucket=minute",
        "since=2020-01-01T00:00:00Z",
        "since=2030-01-01T00:00:00Z&until=2026-01-01T00:00:00Z",
        "since=2026-01-01",
    ],
)
async def test_analytics_validation(admin_harness: AdminHarness, query: str) -> None:
    h = admin_harness
    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/analytics?{query}", headers=h.headers(h.org_key)
    )
    assert response.status_code == 400
