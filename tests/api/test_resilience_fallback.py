import json

import httpx
import pytest

from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, EMBEDDINGS

pytestmark = pytest.mark.respx(assert_all_called=False)


async def test_fallback_order_and_target_options_are_transparent(resilient: ResilientApp) -> None:
    resilient.fallbacks("deepseek/model", "openai/model", "gemini/model")
    resilient.service.settings.max_retries = 0
    order: list[str] = []

    def reply(request: httpx.Request) -> httpx.Response:
        order.append(request.url.host)
        return (
            httpx.Response(200, json={**COMPLETION, "model": "model"})
            if len(order) == 3
            else httpx.Response(503)
        )

    for provider in ("groq", "deepseek", "openai"):
        resilient.router.post(f"https://{provider}.test/v1/chat/completions").mock(
            side_effect=reply
        )
    unused = resilient.router.post("https://gemini.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post(
        "/v1/chat/completions",
        json={
            **CHAT_REQUEST,
            "provider_options": {"groq": {"groq_only": True}, "openai": {"openai_only": True}},
        },
    )

    assert order == ["groq.test", "deepseek.test", "openai.test"]
    assert not unused.called
    payload = json.loads(resilient.router.calls.last.request.content)
    assert payload["model"] == "model"
    assert payload["openai_only"] is True
    assert "groq_only" not in payload
    assert "provider_options" not in payload
    assert response.json()["model"] == "openai/model"
    assert response.headers["x-lgw-fallback-from"] == CHAT_REQUEST["model"]
    assert response.headers["x-lgw-attempts"] == "3"


@pytest.mark.parametrize("skip", ["unconfigured", "open", "incapable"])
async def test_fallback_skips_ineligible_target(resilient: ResilientApp, skip: str) -> None:
    resilient.fallbacks("deepseek/model", "openai/model")
    resilient.service.settings.max_retries = 0
    body = dict(CHAT_REQUEST)
    if skip == "unconfigured":
        del resilient.service.registry.adapters["deepseek"]
    elif skip == "open":
        breaker = resilient.service.breakers["deepseek"]
        resilient.service.settings.breaker_min_calls = 1
        permit = breaker.acquire()
        assert permit is not None
        breaker.finish(permit, True)
    else:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "x", "schema": {"type": "object"}},
        }
    resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    skipped = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    selected = resilient.router.post("https://openai.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    assert skipped.call_count == 0
    assert selected.call_count == 1
    assert response.headers["x-lgw-attempts"] == "2"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 422])
async def test_client_errors_never_fallback(resilient: ResilientApp, status: int) -> None:
    resilient.fallbacks("deepseek/model")
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(status)
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert primary.call_count == 1
    assert fallback.call_count == 0


@pytest.mark.parametrize("opt_out", [True, False])
async def test_fallback_requires_catalogue_and_respects_opt_out(
    resilient: ResilientApp, opt_out: bool
) -> None:
    if opt_out:
        resilient.fallbacks("deepseek/model")
    resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post(
        "/v1/chat/completions",
        json=CHAT_REQUEST,
        headers={"x-lgw-fallback": "disabled"} if opt_out else {},
    )

    assert response.status_code == 502
    assert fallback.call_count == 0


async def test_open_primary_falls_back_without_network(resilient: ResilientApp) -> None:
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.breaker_min_calls = 1
    breaker = resilient.service.breakers["groq"]
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, True)
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    resilient.router.post("https://deepseek.test/v1/chat/completions").respond(200, json=COMPLETION)

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    assert not primary.called
    assert response.headers["x-lgw-attempts"] == "1"
    assert response.headers["x-lgw-fallback-from"] == CHAT_REQUEST["model"]


async def test_embeddings_share_retry_and_fallback_policy(resilient: ResilientApp) -> None:
    price = resilient.service.catalog.find("openai", "embedding", "embedding")
    assert price is not None
    price.fallbacks = ["gemini/embedding"]
    primary = resilient.router.post("https://openai.test/v1/embeddings").respond(503)
    fallback = resilient.router.post("https://gemini.test/v1/embeddings").respond(
        200, json=EMBEDDINGS
    )

    response = await resilient.client.post(
        "/v1/embeddings", json={"model": "openai/embedding", "input": "Hi"}
    )

    assert response.status_code == 200
    assert primary.call_count == 3
    assert fallback.call_count == 1
    assert response.headers["x-lgw-attempts"] == "4"
    assert response.json()["model"].startswith("gemini/")


async def test_fallback_target_gets_its_own_retries(resilient: ResilientApp) -> None:
    resilient.fallbacks("deepseek/model")
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    target = resilient.router.post("https://deepseek.test/v1/chat/completions").mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json=COMPLETION)]
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    assert primary.call_count == 3
    assert target.call_count == 3
    assert response.headers["x-lgw-attempts"] == "6"
    assert resilient.time.delays == [0.125, 0.25, 0.125, 0.25]
