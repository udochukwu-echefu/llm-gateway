import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from llm_gateway.audit.models import AuditEvent
from llm_gateway.tenants.models import AdminIdempotency
from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_team_cursor_keeps_existing_rows_without_duplicates(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    headers = harness.headers(harness.org_key)
    for index in range(3):
        await harness.client.post(
            f"/admin/v1/orgs/{harness.org}/teams", json={"name": f"page-{index}"}, headers=headers
        )
    initial = await harness.client.get(f"/admin/v1/orgs/{harness.org}/teams", headers=headers)
    first = await harness.client.get(
        f"/admin/v1/orgs/{harness.org}/teams?page_size=1", headers=headers
    )
    await harness.client.post(
        f"/admin/v1/orgs/{harness.org}/teams", json={"name": "inserted-later"}, headers=headers
    )
    seen = [first.json()["data"][0]["id"]]
    cursor = first.json()["next_cursor"]
    while cursor is not None:
        response = await harness.client.get(
            f"/admin/v1/orgs/{harness.org}/teams?page_size=1&cursor={cursor}", headers=headers
        )
        seen.extend(row["id"] for row in response.json()["data"])
        cursor = response.json()["next_cursor"]

    assert len(seen) == len(set(seen))
    assert {row["id"] for row in initial.json()["data"]} <= set(seen)


async def test_page_size_over_max_is_rejected(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    response = await harness.client.get(
        "/admin/v1/orgs?page_size=501", headers=harness.headers(harness.platform_key)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


async def test_key_creation_idempotency_replays_original_and_rejects_changed_body(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    headers = harness.headers(harness.org_key) | {"Idempotency-Key": "fake-" + uuid.uuid4().hex}
    path = f"/admin/v1/orgs/{harness.org}/teams/team/keys"
    first = await harness.client.post(path, json={"name": "fake-key"}, headers=headers)
    repeat = await harness.client.post(path, json={"name": "fake-key"}, headers=headers)
    changed = await harness.client.post(path, json={"name": "different-fake-key"}, headers=headers)
    listed = await harness.client.get(f"/admin/v1/orgs/{harness.org}/keys", headers=headers)
    async with harness.sessions() as session:
        events = list(
            (
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "create-key",
                        AuditEvent.target_id == first.json()["key_id"],
                    )
                )
            ).all()
        )
        replay_record = await session.scalar(
            select(AdminIdempotency).where(AdminIdempotency.actor == harness.org_key.split("_")[1])
        )

    assert first.status_code == repeat.status_code == 200
    assert first.json() == repeat.json()
    assert changed.status_code == 409
    assert sum(row["key_id"] == first.json()["key_id"] for row in listed.json()["data"]) == 1
    assert first.json()["key"] not in json.dumps(listed.json())
    assert len(events) == 1
    assert replay_record is not None
    assert first.json()["key"] not in json.dumps(replay_record.response)


async def test_budget_requires_decimal_strings(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    path = f"/admin/v1/orgs/{harness.org}/teams/team/budget"
    response = await harness.client.put(
        path, json={"usd": 1.25}, headers=harness.headers(harness.org_key)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


async def test_concurrent_key_creation_retry_returns_one_key(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    headers = harness.headers(harness.org_key) | {"Idempotency-Key": "fake-" + uuid.uuid4().hex}
    path = f"/admin/v1/orgs/{harness.org}/teams/team/keys"

    first, second = await asyncio.gather(
        harness.client.post(path, json={"name": "fake-concurrent"}, headers=headers),
        harness.client.post(path, json={"name": "fake-concurrent"}, headers=headers),
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


async def test_expired_idempotency_key_allows_new_creation(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    headers = harness.headers(harness.org_key) | {"Idempotency-Key": "fake-" + uuid.uuid4().hex}
    path = f"/admin/v1/orgs/{harness.org}/teams/team/keys"
    first = await harness.client.post(path, json={"name": "fake-expired"}, headers=headers)
    async with harness.sessions.begin() as session:
        row = await session.scalar(
            select(AdminIdempotency).where(
                AdminIdempotency.actor == harness.org_key.split("_")[1],
                AdminIdempotency.route == path,
            )
        )
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    second = await harness.client.post(path, json={"name": "fake-expired"}, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["key_id"] != second.json()["key_id"]
