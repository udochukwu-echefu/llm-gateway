"""Catalogue DTOs expose reviewed routing metadata only, to either admin role."""

import pytest

from llm_gateway.catalog import load_catalog
from llm_gateway.guardrails.policy import REGIONS
from tests.admin_api.conftest import AdminHarness
from tests.providers.fixtures import NVIDIA_MODELS

pytestmark = pytest.mark.db


async def test_catalog_shape_and_no_secrets(admin_harness: AdminHarness) -> None:
    h = admin_harness
    for key in (h.platform_key, h.org_key):
        response = await h.client.get("/admin/v1/catalog", headers=h.headers(key))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"models", "aliases", "regions"}
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


async def test_catalog_exposes_authoritative_regions_to_both_roles(
    admin_harness: AdminHarness,
) -> None:
    h = admin_harness
    for key in (h.platform_key, h.org_key):
        response = await h.client.get("/admin/v1/catalog", headers=h.headers(key))
        identity = await h.client.get("/admin/v1/me", headers=h.headers(key))

        assert response.status_code == 200
        assert response.json()["regions"] == list(REGIONS) == identity.json()["regions"]
        assert "sg" in response.json()["regions"]


async def test_catalog_does_not_call_unpriced_models_priced(admin_harness: AdminHarness) -> None:
    h = admin_harness
    response = await h.client.get("/admin/v1/catalog", headers=h.headers(h.platform_key))

    models = {row["name"]: row for row in response.json()["models"]}
    assert all(models[f"nvidia/{model}"]["priced"] is False for model in NVIDIA_MODELS)
    assert models["zai/glm-5.3-flash"]["priced"] is True
