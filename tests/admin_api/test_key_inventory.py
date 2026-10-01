"""Key status/search filters, exact budget text and team summary metadata."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from llm_gateway.tenants.models import ApiKey
from tests.admin_api.conftest import AdminHarness
from tests.admin_api.test_requests import add_receipts

pytestmark = pytest.mark.db


async def test_key_search_status_filters_and_pagination(admin_harness: AdminHarness) -> None:
    h = admin_harness
    await add_receipts(h)
    async with h.sessions.begin() as session:
        key = await session.scalar(select(ApiKey).where(ApiKey.key_id == h.team_key.split("_")[1]))
        assert key is not None
        key.expires_at = datetime.now(UTC) + timedelta(days=3)
    base = f"/admin/v1/orgs/{h.org}/keys"
    headers = h.headers(h.org_key)
    expiring = (await h.client.get(base + "?status=expiring", headers=headers)).json()
    assert expiring["total"] == 1
    assert expiring["data"][0]["last_used_at"] is not None
    active = (await h.client.get(base + "?status=active&q=fake-client", headers=headers)).json()
    assert active["total"] == 1
    never = (await h.client.get(base + "?status=never-used", headers=headers)).json()
    assert never["total"] == 0
    assert (await h.client.get(base + "?unknown=x", headers=headers)).status_code == 400
    assert (await h.client.get(base + "?status=fake", headers=headers)).status_code == 400
    assert (
        await h.client.get(f"/admin/v1/orgs/{h.other}/keys", headers=headers)
    ).status_code == 404


async def test_entered_budget_keeps_precision_and_team_activity_summary(
    admin_harness: AdminHarness,
) -> None:
    h = admin_harness
    headers = h.headers(h.org_key)
    base = f"/admin/v1/orgs/{h.org}"
    response = await h.client.put(
        base + "/teams/team/budget", json={"usd": "0025.0000", "alert_at": "0.8"}, headers=headers
    )
    assert response.status_code == 200
    loaded = (await h.client.get(base + "/teams/team/budget", headers=headers)).json()
    assert loaded["display_usd"] == "0025.0000"
    await add_receipts(h)
    teams = (await h.client.get(base + "/teams", headers=headers)).json()
    assert teams["total"] == 1
    assert teams["data"][0]["spend_usd"] == "0.000000000003"
    assert teams["data"][0]["key_count"] == 1
    assert teams["data"][0]["last_activity"] is not None


async def test_audit_filters_from_and_to_actor_target_and_count(
    admin_harness: AdminHarness,
) -> None:
    h = admin_harness
    headers = h.headers(h.org_key)
    response = await h.client.get(
        "/admin/v1/audit",
        params={
            "action": "create-team",
            "target_type": "team",
            "actor": "cli-test",
            "since": "2000-01-01",
            "until": "2099-01-01",
        },
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["data"][0]["action"] == "create-team"
    assert (
        await h.client.get("/admin/v1/audit?since=2099-01-01&until=2000-01-01", headers=headers)
    ).status_code == 400
