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


CASES = [
    Case("POST", "/orgs", {"name": "created"}, True, False),
    Case("GET", "/orgs", scoped=False),
    Case("POST", "/orgs/{org}/teams", {"name": "new-team"}),
    Case("GET", "/orgs/{org}/teams"),
    Case("POST", "/orgs/{org}/teams/{team}/keys", {"name": "new-key"}),
    Case("GET", "/orgs/{org}/keys"),
    Case("POST", "/keys/{key_id}/revoke"),
    Case("PUT", "/orgs/{org}/teams/{team}/limits", {"rpm": 7}),
    Case("DELETE", "/orgs/{org}/teams/{team}/limits"),
    Case("PUT", "/orgs/{org}/teams/{team}/budget", {"usd": "1.250000000001"}),
    Case("PUT", "/orgs/{org}/model-policy", {"allow": []}),
    Case("DELETE", "/orgs/{org}/model-policy"),
    Case("PUT", "/orgs/{org}/guardrails", {"actions": []}),
    Case("DELETE", "/orgs/{org}/guardrails"),
    Case("PUT", "/orgs/{org}/residency", {"regions": []}),
    Case("DELETE", "/orgs/{org}/residency"),
    Case("GET", "/orgs/{org}/usage"),
    Case("POST", "/orgs/{org}/cache/purge"),
    Case("GET", "/audit", scoped=False),
    Case("GET", "/audit/verify", platform_only=True, scoped=False),
]


def path(case: Case, harness: AdminHarness, *, other: bool = False) -> str:
    org = harness.other if other else harness.org
    key = harness.other_team_key if other else harness.team_key
    return "/admin/v1" + case.route.format(org=org, team="team", key_id=key.split("_")[1])


def test_matrix_covers_every_admin_route(admin_harness: AdminHarness) -> None:
    app = admin_harness.app
    registered = {
        (method.upper(), route.removeprefix("/admin/v1"))
        for route, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert registered == {(case.method, case.route) for case in CASES}


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.method} {case.route}")
async def test_authorization_matrix(admin_harness: AdminHarness, case: Case) -> None:
    client = admin_harness.client
    own = path(case, admin_harness)
    platform = await client.request(
        case.method, own, json=case.body, headers=admin_harness.headers(admin_harness.platform_key)
    )
    org_body = (
        {"name": "new-team-org"}
        if case.route == "/orgs/{org}/teams" and case.method == "POST"
        else case.body
    )
    org = await client.request(
        case.method, own, json=org_body, headers=admin_harness.headers(admin_harness.org_key)
    )
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
