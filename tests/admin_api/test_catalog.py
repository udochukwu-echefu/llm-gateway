"""Catalogue DTOs expose reviewed routing metadata only, to either admin role."""

import pytest

from llm_gateway.catalog import load_catalog
from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_catalog_shape_and_no_secrets(admin_harness: AdminHarness) -> None:
    h = admin_harness
    for key in (h.platform_key, h.org_key):
        response = await h.client.get("/admin/v1/catalog", headers=h.headers(key))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"models", "aliases"}
        assert {row["name"] for row in body["models"]} == {
            f"{entry.provider}/{entry.model}" for entry in load_catalog().models
        }
        for row in body["models"]:
            assert set(row) == {"name", "provider", "region", "endpoints", "priced"}
            assert row["endpoints"] in (["chat"], ["embeddings"])
            assert isinstance(row["priced"], bool)
        assert set(body["aliases"]) == set(load_catalog().aliases)
        for targets in body["aliases"].values():
            assert all(set(target) == {"model", "weight"} for target in targets)
        assert "http" not in response.text
        assert "lgwa_" not in response.text
        assert "api_key" not in response.text
