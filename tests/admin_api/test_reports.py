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


async def test_redis_outage_returns_503_without_audit_or_scope_leak(
    admin_harness: AdminHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from redis.exceptions import ConnectionError
    from sqlalchemy import func, select

    from llm_gateway.audit.models import AuditEvent

    async def unavailable(*args: object, **kwargs: object) -> int:
        raise ConnectionError("obviously fake Redis outage")

    h = admin_harness
    monkeypatch.setattr("llm_gateway.admin.service.service.AdminService.purge_cache", unavailable)
    async with h.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(AuditEvent))
    own = await h.client.post(f"/admin/v1/orgs/{h.org}/cache/purge", headers=h.headers(h.org_key))
    other = await h.client.post(
        f"/admin/v1/orgs/{h.other}/cache/purge", headers=h.headers(h.org_key)
    )

    assert own.status_code == 503
    assert own.json()["error"]["code"] == "cache_unavailable"
    assert other.status_code == 404
    async with h.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == count
