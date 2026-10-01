"""One route inventory and role matrix for every private endpoint."""

from dataclasses import dataclass
from typing import Literal

import pytest

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


@dataclass(frozen=True)
class Case:
    method: str
    route: str
    body: dict[str, object] | None = None
    platform_only: bool = False
    scoped: bool = True
    conditional: bool = False
    viewer: Literal["read", "deny"] | None = None


CASES = [
    Case("GET", "/me", scoped=False, viewer="read"),
    Case("GET", "/catalog", scoped=False, viewer="read"),
    Case("GET", "/search?q=fake", scoped=False, viewer="read"),
    Case("GET", "/settings", platform_only=True, scoped=False, viewer="read"),
    Case("GET", "/providers", platform_only=True, scoped=False, viewer="read"),
    Case("GET", "/orgs/{org}/requests", viewer="read"),
    Case("GET", "/orgs/{org}/requests/{request_id}", viewer="read"),
    Case("GET", "/orgs/{org}/analytics", viewer="read"),
    Case("POST", "/orgs", {"name": "created"}, True, False, viewer="deny"),
    Case("GET", "/orgs", scoped=False, viewer="read"),
    Case("POST", "/orgs/{org}/teams", {"name": "new-team"}, viewer="deny"),
    Case("GET", "/orgs/{org}/teams", viewer="read"),
    Case("POST", "/orgs/{org}/teams/{team}/keys", {"name": "new-key"}, viewer="deny"),
    Case("GET", "/orgs/{org}/keys", viewer="read"),
    Case("POST", "/keys/{key_id}/revoke", viewer="deny"),
    Case("PUT", "/orgs/{org}/teams/{team}/limits", {"rpm": 7}, viewer="deny"),
    Case("GET", "/orgs/{org}/teams/{team}/limits", viewer="read"),
    Case("DELETE", "/orgs/{org}/teams/{team}/limits", viewer="deny"),
    Case("PUT", "/orgs/{org}/teams/{team}/budget", {"usd": "1.250000000001"}, viewer="deny"),
    Case("GET", "/orgs/{org}/teams/{team}/budget", viewer="read"),
    Case("PUT", "/orgs/{org}/model-policy", {"allow": []}, viewer="deny"),
    Case("GET", "/orgs/{org}/model-policy", viewer="read"),
    Case("DELETE", "/orgs/{org}/model-policy", viewer="deny"),
    Case("PUT", "/orgs/{org}/guardrails", {"actions": []}, viewer="deny"),
    Case("GET", "/orgs/{org}/guardrails", viewer="read"),
    Case("DELETE", "/orgs/{org}/guardrails", viewer="deny"),
    Case("PUT", "/orgs/{org}/residency", {"regions": []}, viewer="deny"),
    Case("GET", "/orgs/{org}/residency", viewer="read"),
    Case("DELETE", "/orgs/{org}/residency", viewer="deny"),
    Case("GET", "/orgs/{org}/usage", viewer="read"),
    Case("POST", "/orgs/{org}/cache/purge", viewer="deny"),
    Case("GET", "/audit", scoped=False, viewer="read"),
    Case("GET", "/audit/verify", platform_only=True, scoped=False, viewer="read"),
]

CASES.extend(
    [
        Case(case.method, case.route, case.body, conditional=True, viewer=case.viewer)
        for case in CASES
        if case.method in ("PUT", "DELETE")
        and case.route.endswith(("model-policy", "guardrails", "residency"))
    ]
)


def path(case: Case, harness: AdminHarness, *, other: bool = False) -> str:
    org = harness.other if other else harness.org
    key = harness.other_team_key if other else harness.team_key
    return "/admin/v1" + case.route.format(
        org=org, team="team", key_id=key.split("_")[1], request_id="fake-matrix-request"
    )


def test_matrix_covers_every_admin_route(admin_harness: AdminHarness) -> None:
    app = admin_harness.app
    registered = {
        (method.upper(), route.removeprefix("/admin/v1"))
        for route, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert registered == {(case.method, case.route.split("?")[0]) for case in CASES}
    assert all(case.viewer in {"read", "deny"} for case in CASES)


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: f"{case.method} {case.route}" + (" If-Match" if case.conditional else ""),
)
async def test_authorization_matrix(admin_harness: AdminHarness, case: Case) -> None:
    if "{request_id}" in case.route:
        from tests.admin_api.usage_fixtures import add_receipts

        await add_receipts(admin_harness, "fake-matrix-request")
    client = admin_harness.client
    own = path(case, admin_harness)
    headers = admin_harness.headers(admin_harness.platform_key)
    if case.conditional:
        loaded = (await client.get(own, headers=headers)).json()
        headers["If-Match"] = f'"{loaded["version"]}"'
    platform = await client.request(case.method, own, json=case.body, headers=headers)
    org_body = (
        {"name": "new-team-org"}
        if case.route == "/orgs/{org}/teams" and case.method == "POST"
        else case.body
    )
    org_headers = admin_harness.headers(admin_harness.org_key)
    if case.conditional:
        loaded = (await client.get(own, headers=org_headers)).json()
        org_headers["If-Match"] = f'"{loaded["version"]}"'
    org = await client.request(case.method, own, json=org_body, headers=org_headers)
    other = (
        await client.request(
            case.method,
            path(case, admin_harness, other=True),
            json=case.body,
            headers=admin_harness.headers(admin_harness.org_key),
        )
        if case.scoped
        else None
    )
    missing = await client.request(case.method, own, json=case.body)

    assert platform.status_code == 200
    assert org.status_code == (403 if case.platform_only else 200)
    if other is not None:
        assert other.status_code == 404
    assert missing.status_code == 401


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.route}")
@pytest.mark.parametrize("scoped", [False, True], ids=["platform-viewer", "org-viewer"])
async def test_viewer_authorization_matrix(
    admin_harness: AdminHarness, case: Case, scoped: bool
) -> None:
    from sqlalchemy import text

    if "{request_id}" in case.route:
        from tests.admin_api.usage_fixtures import add_receipts

        await add_receipts(admin_harness, "fake-matrix-request")
    key = admin_harness.org_viewer_key if scoped else admin_harness.viewer_key
    headers = admin_harness.headers(key)
    headers["Idempotency-Key"] = "viewer-must-not-create-a-record"
    headers["If-Match"] = '"' + "0" * 64 + '"'
    # Hash all mutable admin state, including audit and replay rows, without exposing secrets.
    query = text("""
        SELECT md5(string_agg(value, '' ORDER BY value)) FROM (
            SELECT row_to_json(t)::text AS value FROM organizations t UNION ALL
            SELECT row_to_json(t)::text FROM teams t UNION ALL
            SELECT row_to_json(t)::text FROM api_keys t UNION ALL
            SELECT row_to_json(t)::text FROM admin_keys t UNION ALL
            SELECT row_to_json(t)::text FROM team_limits t UNION ALL
            SELECT row_to_json(t)::text FROM audit_events t UNION ALL
            SELECT row_to_json(t)::text FROM admin_idempotency t
        ) state
    """)
    async with admin_harness.sessions() as session:
        before = await session.scalar(query)
    response = await admin_harness.client.request(
        case.method, path(case, admin_harness), json=case.body, headers=headers
    )
    expected = 403 if case.viewer == "deny" or (scoped and case.platform_only) else 200
    assert response.status_code == expected
    if case.viewer == "deny":
        assert response.json()["error"]["code"] == "read_only_admin"
    async with admin_harness.sessions() as session:
        assert await session.scalar(query) == before
    if scoped and case.scoped and case.viewer == "read":
        other = await admin_harness.client.get(
            path(case, admin_harness, other=True), headers=headers
        )
        assert other.status_code == 404
