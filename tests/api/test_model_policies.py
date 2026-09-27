from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from llm_gateway.gateway_state import get_app_state
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION

SetPolicy = Callable[[tuple[str, ...] | None, tuple[str, ...] | None], None]


async def test_denied_model_precedes_limits_and_never_calls_provider(
    resilient: ResilientApp, set_policy: SetPolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_policy(("groq/*",), ("deepseek/*",))
    limits = get_app_state(resilient.app).limits
    assert limits is not None
    admission = AsyncMock(return_value=(None, {}))
    monkeypatch.setattr(limits, "admission", admission)
    route = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "deepseek/model"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "model_not_allowed"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "deepseek/model" in response.json()["error"]["message"]
    assert "groq/" not in response.json()["error"]["message"]
    assert not route.called
    admission.assert_not_awaited()
    assert not resilient.records


async def test_open_breaker_never_falls_back_to_forbidden_provider(
    resilient: ResilientApp, set_policy: SetPolicy
) -> None:
    set_policy(("groq/*",), None)
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.breaker_min_calls = 1
    breaker = resilient.service.breakers["groq"]
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, True)
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    forbidden = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert not forbidden.called
    assert not primary.called
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


async def test_provider_options_cannot_override_authorized_model(
    resilient: ResilientApp, set_policy: SetPolicy
) -> None:
    set_policy(("groq/*",), None)
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post(
        "/v1/chat/completions",
        json={**CHAT_REQUEST, "provider_options": {"groq": {"model": "deepseek/model"}}},
    )

    assert response.status_code == 400
    assert not route.called


async def test_policy_changes_take_effect_at_original_cache_ttl(
    resilient: ResilientApp, set_policy: SetPolicy
) -> None:
    state = get_app_state(resilient.app)
    state.key_cache.clock = resilient.time.clock
    state.key_cache.ttl = 30
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    first = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    set_policy(("deepseek/*",), None)
    resilient.time.now = 29

    cached = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    resilient.time.now = 30
    denied = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert first.status_code == cached.status_code == 200
    assert denied.status_code == 403
    assert route.call_count == 2


@pytest.mark.parametrize(
    ("org", "team", "providers", "aliases"),
    [
        (None, None, {"groq", "deepseek", "openai", "gemini"}, {"fast", "private", "embed"}),
        (("groq/*",), None, {"groq"}, {"fast"}),
        (None, ("deepseek/*",), {"deepseek"}, {"fast", "private"}),
        (("groq/*",), ("groq/*", "deepseek/*"), {"groq"}, {"fast"}),
        (("groq/*",), ("deepseek/*",), set[str](), set[str]()),
    ],
)
async def test_model_list_respects_team_intersection_and_alias_targets(
    aliased: ResilientApp,
    set_policy: SetPolicy,
    org: tuple[str, ...] | None,
    team: tuple[str, ...] | None,
    providers: set[str],
    aliases: set[str],
) -> None:
    set_policy(org, team)

    response = await aliased.client.get("/v1/models")

    assert response.status_code == 200
    ids = {entry["id"] for entry in response.json()["data"]}
    assert {name.split("/")[0] for name in ids if "/" in name} == providers
    assert {name for name in ids if "/" not in name} == aliases
