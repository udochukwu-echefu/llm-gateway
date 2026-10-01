"""One route inventory and role matrix for every private endpoint."""

from dataclasses import dataclass

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


CASES = [
    Case("GET", "/me", scoped=False),
    Case("GET", "/catalog", scoped=False),
    Case("GET", "/search?q=fake", scoped=False),
    Case("GET", "/settings", platform_only=True, scoped=False),
    Case("GET", "/providers", platform_only=True, scoped=False),
    Case("GET", "/orgs/{org}/requests"),
    Case("GET", "/orgs/{org}/requests/{request_id}"),
    Case("GET", "/orgs/{org}/analytics"),
    Case("POST", "/orgs", {"name": "created"}, True, False),
    Case("GET", "/orgs", scoped=False),
    Case("POST", "/orgs/{org}/teams", {"name": "new-team"}),
    Case("GET", "/orgs/{org}/teams"),
    Case("POST", "/orgs/{org}/teams/{team}/keys", {"name": "new-key"}),
    Case("GET", "/orgs/{org}/keys"),
    Case("POST", "/keys/{key_id}/revoke"),
    Case("PUT", "/orgs/{org}/teams/{team}/limits", {"rpm": 7}),
    Case("GET", "/orgs/{org}/teams/{team}/limits"),
    Case("DELETE", "/orgs/{org}/teams/{team}/limits"),
    Case("PUT", "/orgs/{org}/teams/{team}/budget", {"usd": "1.250000000001"}),
    Case("GET", "/orgs/{org}/teams/{team}/budget"),
    Case("PUT", "/orgs/{org}/model-policy", {"allow": []}),
    Case("GET", "/orgs/{org}/model-policy"),
    Case("DELETE", "/orgs/{org}/model-policy"),
    Case("PUT", "/orgs/{org}/guardrails", {"actions": []}),
    Case("GET", "/orgs/{org}/guardrails"),
    Case("DELETE", "/orgs/{org}/guardrails"),
    Case("PUT", "/orgs/{org}/residency", {"regions": []}),
    Case("GET", "/orgs/{org}/residency"),
    Case("DELETE", "/orgs/{org}/residency"),
    Case("GET", "/orgs/{org}/usage"),
    Case("POST", "/orgs/{org}/cache/purge"),
    Case("GET", "/audit", scoped=False),
    Case("GET", "/audit/verify", platform_only=True, scoped=False),
]

CASES.extend(
    [
        Case(case.method, case.route, case.body, conditional=True)
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
