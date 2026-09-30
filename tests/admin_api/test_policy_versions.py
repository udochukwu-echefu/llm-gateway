"""HTTP conditional writes preserve data and audit history under stale/racing editors."""

import asyncio

import pytest
from sqlalchemy import func, select

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.models import AuditEvent
from tests.admin_api.conftest import AdminHarness
from tests.conftest import TEST_PEPPER

pytestmark = pytest.mark.db
POLICIES = [
    ("model-policy", {"allow": ["groq/*"]}),
    ("guardrails", {"actions": ["email=block"]}),
    ("residency", {"regions": ["eu"]}),
]


async def audit_count(harness: AdminHarness) -> int:
    async with harness.sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(AuditEvent)) or 0)


@pytest.mark.parametrize(("kind", "body"), POLICIES)
@pytest.mark.parametrize("team", [False, True], ids=["org", "team"])
async def test_fresh_stale_clear_and_repeated_writes(
    admin_harness: AdminHarness, kind: str, body: dict[str, list[str]], team: bool
) -> None:
    h = admin_harness
    path = f"/admin/v1/orgs/{h.org}/{kind}" + ("?team=team" if team else "")
    headers = h.headers(h.org_key)
    loaded = (await h.client.get(path, headers=headers)).json()
    first = await h.client.put(
        path, json=body, headers={**headers, "If-Match": f'"{loaded["version"]}"'}
    )
    saved = (await h.client.get(path, headers=headers)).json()
    count = await audit_count(h)

    assert first.status_code == 200
    assert saved["version"] != loaded["version"]
    for method in ("PUT", "DELETE"):
        stale = await h.client.request(
            method,
            path,
            json=body if method == "PUT" else None,
            headers={**headers, "If-Match": f'"{loaded["version"]}"'},
        )
        assert stale.status_code == 412
        assert stale.json()["error"]["code"] == "policy_version_conflict"
        assert (await h.client.get(path, headers=headers)).json() == saved
        assert await audit_count(h) == count
    repeated = await h.client.put(
        path, json=body, headers={**headers, "If-Match": f'"{saved["version"]}"'}
    )
    newest = (await h.client.get(path, headers=headers)).json()
    assert repeated.status_code == 200
    assert newest["version"] != saved["version"]
    for _ in range(2):
        cleared = await h.client.delete(
            path, headers={**headers, "If-Match": f'"{newest["version"]}"'}
        )
        current = (await h.client.get(path, headers=headers)).json()
        assert cleared.status_code == 200
        assert current["version"] != newest["version"]
        newest = current
    assert newest["version"] != loaded["version"]


@pytest.mark.parametrize(("kind", "body"), POLICIES)
@pytest.mark.parametrize("team", [False, True], ids=["org", "team"])
async def test_same_version_racing_writers_have_exactly_one_success(
    admin_harness: AdminHarness, kind: str, body: dict[str, list[str]], team: bool
) -> None:
    h = admin_harness
    path = f"/admin/v1/orgs/{h.org}/{kind}" + ("?team=team" if team else "")
    headers = h.headers(h.org_key)
    loaded = (await h.client.get(path, headers=headers)).json()
    headers["If-Match"] = f'"{loaded["version"]}"'
    count = await audit_count(h)

    replies = await asyncio.gather(
        *(h.client.put(path, json=body, headers=headers) for _ in range(2))
    )

    assert sorted(response.status_code for response in replies) == [200, 412]
    assert await audit_count(h) == count + 1


@pytest.mark.parametrize("invalid", ["*", '"short"', "a" * 64, 'W/"' + "a" * 64 + '"'])
async def test_invalid_if_match_is_rejected(admin_harness: AdminHarness, invalid: str) -> None:
    h = admin_harness
    response = await h.client.put(
        f"/admin/v1/orgs/{h.org}/model-policy",
        json={"allow": []},
        headers={**h.headers(h.org_key), "If-Match": invalid},
    )
    assert response.status_code == 400


async def test_cli_write_invalidates_console_version(admin_harness: AdminHarness) -> None:
    h = admin_harness
    path = f"/admin/v1/orgs/{h.org}/guardrails"
    headers = h.headers(h.org_key)
    loaded = (await h.client.get(path, headers=headers)).json()
    admin = AdminService(h.sessions, TEST_PEPPER.encode(), "fake-cli")
    await admin.set_policy(h.org, None, residency=False, values=["email=block"])

    response = await h.client.delete(
        path, headers={**headers, "If-Match": f'"{loaded["version"]}"'}
    )

    assert response.status_code == 412
    assert (await h.client.get(path, headers=headers)).json()["effective"]["email"] == "block"
