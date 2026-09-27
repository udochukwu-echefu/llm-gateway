import asyncio

import httpx
from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from llm_gateway.gateway_state import get_app_state
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION


def registry(app: FastAPI) -> CollectorRegistry:
    telemetry = get_app_state(app).telemetry
    assert telemetry is not None
    return telemetry.metrics.registry


async def test_success_and_4xx_metrics_and_private_metrics_port(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    response = await client.get("/metrics")
    await client.post("/v1/chat/completions", json={})

    assert response.status_code == 404
    metrics = registry(app)
    assert (
        metrics.get_sample_value("lgw_requests_total", {"route": "other", "status_class": "4xx"})
        == 1
    )
    assert (
        metrics.get_sample_value(
            "lgw_requests_total", {"route": "/v1/chat/completions", "status_class": "4xx"}
        )
        == 1
    )
    assert metrics.get_sample_value("lgw_inflight_requests", {"route": "/v1/chat/completions"}) == 0


async def test_retry_fallback_tokens_cost_and_breaker_metrics(resilient: ResilientApp) -> None:
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.max_retries = 1
    resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    resilient.router.post("https://deepseek.test/v1/chat/completions").respond(200, json=COMPLETION)

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    metrics = registry(resilient.app)
    assert (
        metrics.get_sample_value(
            "lgw_upstream_requests_total",
            {"provider": "groq", "model": "llama-3.3-70b-versatile", "outcome": "upstream_error"},
        )
        == 2
    )
    assert (
        metrics.get_sample_value(
            "lgw_retries_total", {"provider": "groq", "reason": "upstream_server_error"}
        )
        == 1
    )
    assert (
        metrics.get_sample_value(
            "lgw_fallbacks_total", {"from_provider": "groq", "to_provider": "deepseek"}
        )
        == 1
    )
    assert (
        metrics.get_sample_value(
            "lgw_tokens_total", {"provider": "deepseek", "model": "model", "kind": "prompt"}
        )
        == 9
    )
    assert (
        metrics.get_sample_value("lgw_cost_usd_total", {"provider": "deepseek", "model": "model"})
        == 0.000000975
    )
    resilient.service.settings.retry_budget_min_per_window = 10
    for _ in range(4):
        await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    assert metrics.get_sample_value("lgw_circuit_state", {"provider": "groq"}) == 2


async def test_overhead_excludes_known_provider_delay(resilient: ResilientApp) -> None:
    async def delayed(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return httpx.Response(200, json=COMPLETION)

    resilient.router.post("https://groq.test/v1/chat/completions").mock(side_effect=delayed)

    await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    metrics = registry(resilient.app)
    labels = {"route": "/v1/chat/completions"}
    duration = metrics.get_sample_value("lgw_request_duration_seconds_sum", labels)
    overhead = metrics.get_sample_value("lgw_gateway_overhead_seconds_sum", labels)
    assert duration is not None
    assert overhead is not None
    assert duration >= 0.1
    assert duration - overhead >= 0.1
    assert overhead < 0.08


async def test_auth_failure_is_counted_without_identity_labels(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    response = await client.get("/v1/models", headers={"authorization": "invalid"})

    assert response.status_code == 401
    assert (
        registry(app).get_sample_value(
            "lgw_auth_failures_total", {"reason": "missing_or_malformed"}
        )
        == 1
    )
