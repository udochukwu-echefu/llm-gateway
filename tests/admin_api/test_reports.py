"""HTTP JSON preserves unknown accounting values instead of inventing prices."""

import pytest

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_unpriced_usage_is_json_null(
    admin_harness: AdminHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unpriced(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [{"group": "fake-model", "cost_usd": None, "saved_usd": None}]

    monkeypatch.setattr("llm_gateway.admin.service.service.AdminService.usage", unpriced)
    response = await admin_harness.client.get(
        f"/admin/v1/orgs/{admin_harness.org}/usage?group_by=model",
        headers=admin_harness.headers(admin_harness.org_key),
    )

    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["cost_usd"] is None
    assert row["saved_usd"] is None
