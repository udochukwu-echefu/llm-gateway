from collections.abc import Callable

import pytest

from llm_gateway.guardrails.policy import Region
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION

SetResidency = Callable[[tuple[Region, ...] | None], None]


@pytest.mark.parametrize("model", ["deepseek/model", "private", "fast"])
async def test_direct_alias_and_weighted_route_deny_all_regions(
    aliased: ResilientApp, set_residency: SetResidency, model: str
) -> None:
    set_residency(("eu",))

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": model}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "model_not_allowed"
    assert not aliased.router.calls
    assert not aliased.records
    if "/" in model:
        assert "region 'cn' is not permitted" in response.json()["error"]["message"]


async def test_weighted_route_filters_region_before_draw(
    aliased: ResilientApp, set_residency: SetResidency
) -> None:
    set_residency(("us",))
    aliased.service.routing_random = lambda: 0.999
    allowed = aliased.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"}
    )

    assert response.status_code == 200
    assert allowed.call_count == 1


async def test_fallback_cannot_bypass_residency(
    resilient: ResilientApp, set_residency: SetResidency
) -> None:
    set_residency(("us",))
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.max_retries = 0
    resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    denied = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 502
    assert not denied.called


async def test_models_hides_disallowed_regions_and_aliases(
    aliased: ResilientApp, set_residency: SetResidency
) -> None:
    set_residency(("us",))

    response = await aliased.client.get("/v1/models")

    names = {row["id"] for row in response.json()["data"]}
    assert "fast" in names
    assert "private" not in names
    assert "embed" not in names
    assert all(name.startswith("groq/") for name in names if "/" in name)
