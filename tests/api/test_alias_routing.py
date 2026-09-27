import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from llm_gateway.gateway_state import get_app_state
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, EMBEDDINGS, STREAM, sse

SetPolicy = Callable[[tuple[str, ...] | None, tuple[str, ...] | None], None]


async def test_fixed_draws_select_expected_weighted_targets(aliased: ResilientApp) -> None:
    sequence = iter([0.0, 0.89999, 0.9, 0.99999])
    aliased.service.routing_random = lambda: next(sequence)
    groq = aliased.router.post("https://groq.test/v1/chat/completions").respond(
        200, json={**COMPLETION, "model": "model"}
    )
    deepseek = aliased.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json={**COMPLETION, "model": "model"}
    )

    responses = [
        await aliased.client.post("/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"})
        for _ in range(4)
    ]

    assert [r.json()["model"] for r in responses] == [
        "groq/model",
        "groq/model",
        "deepseek/model",
        "deepseek/model",
    ]
    assert all(r.headers["x-lgw-alias"] == "fast" for r in responses)
    assert all("x-lgw-fallback-from" not in r.headers for r in responses)
    assert groq.call_count == deepseek.call_count == 2
    assert json.loads(groq.calls.last.request.content)["model"] == "model"


@pytest.mark.parametrize("draw", [0.0, 0.9, 0.99999])
async def test_alias_checks_concrete_target_and_removes_forbidden_weights(
    aliased: ResilientApp, set_policy: SetPolicy, draw: float
) -> None:
    set_policy(("groq/model",), None)
    aliased.service.routing_random = lambda: draw
    allowed = aliased.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    forbidden = aliased.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"}
    )

    assert response.status_code == 200
    assert allowed.called
    assert not forbidden.called


async def test_alias_with_all_targets_forbidden_returns_403(
    aliased: ResilientApp, set_policy: SetPolicy
) -> None:
    set_policy(("gemini/*",), None)
    route = aliased.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "model_not_allowed"
    assert not route.called


async def test_unknown_alias_lists_only_allowed_aliases(
    aliased: ResilientApp, set_policy: SetPolicy
) -> None:
    set_policy(("groq/*",), None)

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "unknown-alias"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    message = response.json()["error"]["message"]
    assert "Available aliases: fast." in message
    assert "private" not in message
    assert "embed" not in message


async def test_alias_is_recorded_on_every_attempt_and_metric(aliased: ResilientApp) -> None:
    aliased.service.routing_random = lambda: 0.0
    price = aliased.service.catalog.find("groq", "model", "chat")
    assert price is not None
    price.fallbacks = ["deepseek/model"]
    aliased.service.settings.max_retries = 1
    aliased.router.post("https://groq.test/v1/chat/completions").respond(503)
    aliased.router.post("https://deepseek.test/v1/chat/completions").respond(200, json=COMPLETION)

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"}
    )
    async with asyncio.timeout(2):
        for _ in range(2000):
            if len(aliased.records) >= 3:
                break
            await asyncio.sleep(0.001)

    assert response.status_code == 200
    assert response.headers["x-lgw-alias"] == "fast"
    assert response.headers["x-lgw-fallback-from"] == "groq/model"
    assert [r.alias for r in aliased.records] == ["fast"] * 3
    assert [r.fallback_from for r in aliased.records] == [None, None, "groq/model"]
    telemetry = get_app_state(aliased.app).telemetry
    assert telemetry is not None
    for provider, outcome, count in [("groq", "upstream_error", 2), ("deepseek", "success", 1)]:
        assert (
            telemetry.metrics.registry.get_sample_value(
                "lgw_upstream_requests_total",
                {"provider": provider, "model": "model", "outcome": outcome, "alias": "fast"},
            )
            == count
        )


async def test_stream_alias_header_and_concrete_chunks(aliased: ResilientApp) -> None:
    aliased.service.routing_random = lambda: 0.0
    aliased.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=b"".join(sse(*STREAM, "[DONE]")))
    )

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast", "stream": True}
    )

    assert response.status_code == 200
    assert response.headers["x-lgw-alias"] == "fast"
    assert "groq/" in response.text
    assert '"model":"fast"' not in response.text
    assert response.text.endswith("data: [DONE]\n\n")


async def test_embedding_alias_resolves_to_concrete_model(aliased: ResilientApp) -> None:
    route = aliased.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)

    response = await aliased.client.post("/v1/embeddings", json={"model": "embed", "input": "Hi"})

    assert response.status_code == 200
    assert response.headers["x-lgw-alias"] == "embed"
    assert response.json()["model"].startswith("openai/")
    assert json.loads(route.calls.last.request.content)["model"] == "embedding"


async def test_unconfigured_alias_target_cannot_win_or_appear_in_discovery(
    aliased: ResilientApp,
) -> None:
    del aliased.service.registry.adapters["deepseek"]
    aliased.service.routing_random = lambda: 0.999
    allowed = aliased.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "fast"}
    )
    listed = await aliased.client.get("/v1/models")
    private = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "private"}
    )

    assert response.status_code == 200
    assert allowed.called
    assert "private" not in {item["id"] for item in listed.json()["data"]}
    assert private.status_code == 404
    assert private.json()["error"]["code"] == "model_not_found"


async def test_resolved_alias_header_survives_validation_error(aliased: ResilientApp) -> None:
    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "embed"}
    )

    assert response.status_code == 404
    assert response.headers["x-lgw-alias"] == "embed"


async def test_unknown_alias_never_becomes_a_metric_label(aliased: ResilientApp) -> None:
    unknown = "untrusted-label-sentinel"

    response = await aliased.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": unknown}
    )

    assert response.status_code == 404
    telemetry = get_app_state(aliased.app).telemetry
    assert telemetry is not None
    assert all(
        unknown not in str(sample.labels)
        for metric in telemetry.metrics.registry.collect()
        for sample in metric.samples
    )
