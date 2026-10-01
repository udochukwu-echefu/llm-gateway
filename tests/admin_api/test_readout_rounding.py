"""Readout precision is checked through every timing HTTP surface."""

import pytest
from sqlalchemy import update

from llm_gateway.usage.repository import UsageRow
from tests.admin_api.conftest import AdminHarness
from tests.admin_api.usage_fixtures import add_receipts

pytestmark = pytest.mark.db


@pytest.mark.parametrize(
    "value", [1724.9999999999998, 880.0000000000001, 24200.000000000004, 50599.99999999999]
)
async def test_timing_readouts_round_artifacts(admin_harness: AdminHarness, value: float) -> None:
    h = admin_harness
    await add_receipts(h)
    async with h.sessions() as session:
        await session.execute(
            update(UsageRow).values(duration_ms=value, ttfb_ms=value, status_code=200)
        )
        await session.execute(update(UsageRow).where(UsageRow.attempt == 1).values(status_code=502))
        await session.commit()

    base = f"/admin/v1/orgs/{h.org}"
    headers = h.headers(h.org_key)
    for path in ("/requests", "/requests/fake-chain"):
        response = await h.client.get(base + path, headers=headers)
        assert response.status_code == 200
        for row in response.json()["data"]:
            assert row["duration_ms"] == round(value, 1)
            assert row["ttfb_ms"] == round(value, 1)
    response = await h.client.get(base + "/analytics", headers=headers)
    row = response.json()["data"][0]
    assert float(row["error_rate"]) == pytest.approx(1 / 3)
    for name in ("duration", "ttfb"):
        for percentile in ("p50", "p95", "p99"):
            assert row[f"{name}_{percentile}"] == round(value, 1)
    response = await h.client.get("/admin/v1/providers", headers=h.headers(h.platform_key))
    assert response.status_code == 200
    groq = next(row for row in response.json()["data"] if row["provider"] == "groq")
    assert groq["15m"]["p95_ms"] == round(value, 1)
