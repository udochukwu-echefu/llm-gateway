"""Identity is authenticated on the private listener and contains no secrets."""

import pytest

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


@pytest.mark.parametrize("role", ["platform", "org"])
async def test_me_returns_verified_identity(admin_harness: AdminHarness, role: str) -> None:
    harness = admin_harness
    key = harness.platform_key if role == "platform" else harness.org_key

    response = await harness.client.get("/admin/v1/me", headers=harness.headers(key))
    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"key_id", "name", "role", "organization", "regions"}
    assert body["regions"] == ["us", "eu", "cn", "sg", "global", "unknown"]
    assert body["key_id"] == key.split("_")[1]
    assert body["name"] == "fake-" + role
    assert body["role"] == role
    assert key not in response.text
    assert "secret" not in response.text
    if role == "platform":
        assert body["organization"] is None
    else:
        assert body["organization"]["name"] == harness.org
        assert set(body["organization"]) == {"id", "name"}


async def test_me_rejects_revoked_key(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    await harness.client.post(
        f"/admin/v1/keys/{harness.org_key.split('_')[1]}/revoke",
        headers=harness.headers(harness.platform_key),
    )

    response = await harness.client.get("/admin/v1/me", headers=harness.headers(harness.org_key))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_admin_key"
