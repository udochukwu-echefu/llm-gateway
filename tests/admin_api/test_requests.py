"""Metadata list semantics exercised through HTTP against migrated Postgres."""

import pytest
from sqlalchemy import select, text

from llm_gateway.tenants.models import Organization
from tests.admin_api.conftest import AdminHarness
from tests.admin_api.usage_fixtures import add_receipts

pytestmark = pytest.mark.db


async def test_request_pagination_timeline_and_isolation(h: AdminHarness) -> None:
    await add_receipts(h)
    await add_receipts(h, org_name=h.other)
    base = f"/admin/v1/orgs/{h.org}/requests"
    headers = h.headers(h.org_key)
    page = (await h.client.get(base + "?page_size=2", headers=headers)).json()
    assert page["total"] == 3
    assert [row["attempt"] for row in page["data"]] == [3, 2]
    assert page["data"][0]["cost_usd"] == "0.000000000001"
    second = (
        await h.client.get(
            base, params={"page_size": 2, "cursor": page["next_cursor"]}, headers=headers
        )
    ).json()
    assert [row["attempt"] for row in second["data"]] == [1]
    assert second["next_cursor"] is None
    timeline = (await h.client.get(base + "/fake-chain", headers=headers)).json()
    assert [row["attempt"] for row in timeline["data"]] == [1, 2, 3]
    other = await h.client.get(f"/admin/v1/orgs/{h.other}/requests", headers=headers)
    assert other.status_code == 404
    other_detail = await h.client.get(
        f"/admin/v1/orgs/{h.other}/requests/fake-chain", headers=headers
    )
    assert other_detail.status_code == 404
    empty = await h.client.get(base + "/fake-missing", headers=headers)
    assert empty.status_code == 404


@pytest.fixture
async def h(admin_harness: AdminHarness) -> AdminHarness:
    return admin_harness


@pytest.mark.parametrize(
    ("query", "attempts"),
    [
        ({"team": "team"}, [3, 2, 1]),
        ({"provider": "groq"}, [2, 1]),
        ({"model": "fake-model"}, [3, 2, 1]),
        ({"alias": "fake-alias"}, [3, 2, 1]),
        ({"endpoint": "embeddings"}, []),
        ({"status": "5xx"}, [2, 1]),
        ({"status": "200"}, [3]),
        ({"outcome": "success"}, [3]),
        ({"cost_status": "unpriced"}, []),
        ({"stream": "false"}, []),
        ({"cache_hit": "true"}, []),
        ({"redacted": "true"}, [3, 2, 1]),
        ({"fallback": "true"}, [3]),
        ({"retried": "true"}, [3, 2]),
        ({"min_latency": "250"}, [3]),
        ({"since": "2099-01-01T00:00:00Z"}, []),
        ({"until": "2000-01-01T00:00:00Z"}, []),
    ],
)
async def test_request_filters(h: AdminHarness, query: dict[str, str], attempts: list[int]) -> None:
    await add_receipts(h)
    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/requests", params=query, headers=h.headers(h.org_key)
    )
    assert response.status_code == 200
    assert [row["attempt"] for row in response.json()["data"]] == attempts


@pytest.mark.parametrize(
    "query",
    [
        "unknown=x",
        "status=3xx",
        "provider=other",
        "page_size=201",
        "min_latency=nan",
        "since=2026-01-01",
        "stream=1",
        "cursor=bad",
        "team=x&team=y",
        "since=2026-02-01T00:00:00Z&until=2026-01-01T00:00:00Z",
    ],
)
async def test_invalid_request_filters_are_400(h: AdminHarness, query: str) -> None:
    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/requests?{query}", headers=h.headers(h.org_key)
    )
    assert response.status_code == 400


async def test_key_filter_and_last_used(h: AdminHarness) -> None:
    await add_receipts(h)
    key_id = h.team_key.split("_")[1]
    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/requests", params={"key_id": key_id}, headers=h.headers(h.org_key)
    )
    assert len(response.json()["data"]) == 3
    keys = (
        await h.client.get(f"/admin/v1/orgs/{h.org}/keys", headers=h.headers(h.org_key))
    ).json()["data"]
    assert keys[0]["last_used_at"] is not None


async def test_request_indexes_in_query_plans(h: AdminHarness) -> None:
    await add_receipts(h)
    async with h.sessions() as session:
        org = await session.scalar(select(Organization).where(Organization.name == h.org))
        assert org is not None
        # Tiny fixtures naturally favour a sequential scan; disabling it verifies index eligibility.
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = await session.scalars(
            text(
                "EXPLAIN SELECT * FROM usage_records WHERE organization_id=:org "
                "ORDER BY created_at DESC,id DESC LIMIT 50"
            ),
            {"org": org.id},
        )
        assert "ix_usage_org_created_id" in "\n".join(plan)
        timeline = await session.scalars(
            text(
                "EXPLAIN SELECT * FROM usage_records WHERE organization_id=:org "
                "AND request_id='fake-chain' ORDER BY attempt"
            ),
            {"org": org.id},
        )
        assert "ix_usage_org_request_attempt" in "\n".join(timeline)
