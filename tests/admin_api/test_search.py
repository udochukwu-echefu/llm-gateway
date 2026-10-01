"""Search cannot turn public IDs into a cross-organization oracle."""

import pytest

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_search_is_scoped_before_matching_names_and_ids(admin_harness: AdminHarness) -> None:
    h = admin_harness
    for query in (h.other, "team", "fake-client", h.other_team_key.split("_")[1]):
        response = await h.client.get(
            "/admin/v1/search", params={"q": query}, headers=h.headers(h.org_key)
        )
        assert response.status_code == 200
        assert all(item["org"] == h.org for item in response.json()["data"])
    platform = await h.client.get(
        "/admin/v1/search", params={"q": h.other}, headers=h.headers(h.platform_key)
    )
    assert platform.json()["data"][0]["org"] == h.other
    invalid = await h.client.get("/admin/v1/search?q=x&unknown=y", headers=h.headers(h.org_key))
    assert invalid.status_code == 400
