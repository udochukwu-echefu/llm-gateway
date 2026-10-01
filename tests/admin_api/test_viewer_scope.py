"""Global-list scope comes from organization ID, including a viewer's nullable scope."""

from dataclasses import replace

import pytest

from tests.admin_api import test_authorization as matrix
from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


@pytest.mark.parametrize("path", ["/orgs", "/audit"])
async def test_viewer_global_lists_match_the_corresponding_admin_scope(
    admin_harness: AdminHarness, path: str
) -> None:
    h = admin_harness
    org = await h.client.get("/admin/v1" + path, headers=h.headers(h.org_key))
    viewer = await h.client.get("/admin/v1" + path, headers=h.headers(h.org_viewer_key))
    platform = await h.client.get("/admin/v1" + path, headers=h.headers(h.viewer_key))

    assert viewer.status_code == platform.status_code == 200
    assert viewer.json() == org.json()
    assert platform.json()["total"] > viewer.json()["total"]
    if path == "/orgs":
        assert [item["name"] for item in viewer.json()["data"]] == [h.org]


def test_completeness_rejects_an_omitted_viewer_policy(
    admin_harness: AdminHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = list(matrix.CASES)
    cases[0] = replace(cases[0], viewer=None)
    monkeypatch.setattr(matrix, "CASES", cases)

    with pytest.raises(AssertionError):
        matrix.test_matrix_covers_every_admin_route(admin_harness)
