"""Queue wait consumes the request budget without enabling duplicate read retries."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.gateway_state import get_app_state
from tests.conftest import UPSTREAM_KEY
from tests.fixtures import parse_events, sse
from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import hosted_completion, hosted_stream

pytestmark = [
    pytest.mark.parametrize("provider_name", ["nvidia"]),
    pytest.mark.respx(assert_all_called=False),
]
CHAT = {"model": "nvidia/moonshotai/kimi-k3", "messages": [{"role": "user", "content": "Hi"}]}


@pytest.fixture
def hosted_max_retries() -> int:
    return 2


@pytest.fixture
def settings(settings: Settings) -> Settings:
    settings.providers = ProvidersSettings.model_validate(
        {
            "nvidia": {"api_key": UPSTREAM_KEY, "base_url": "https://nvidia.test/v1"},
            "groq": {"api_key": UPSTREAM_KEY, "base_url": "https://groq.test/v1"},
        }
    )
    settings.resilience.deadline_s = 330
    return settings


@pytest.fixture
def elapsed(hosted_gateway: HostedGateway) -> list[float]:
    time = [0.0]
    state = get_app_state(hosted_gateway.app)
    state.resilience.clock = lambda: time[0]
    return time


async def test_three_minute_read_timeout_is_not_retried_or_automatically_failed_over(
    hosted_gateway: HostedGateway,
    respx_mock: respx.MockRouter,
    elapsed: list[float],
) -> None:
    state = get_app_state(hosted_gateway.app)
    assert state.settings.resilience.retry_read_timeouts is False
    price = state.catalog.find("nvidia", "moonshotai/kimi-k3", "chat")
    assert price is not None
    price.fallbacks = ["groq/openai/gpt-oss-20b"]

    def timeout(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == 300
        elapsed[0] = 300
        raise httpx.ReadTimeout("synthetic queued read timeout")

    primary = respx_mock.post("https://nvidia.test/v1/chat/completions").mock(side_effect=timeout)
    fallback = respx_mock.post("https://groq.test/v1/chat/completions")

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    assert primary.call_count == 1
    assert not fallback.called


@pytest.mark.parametrize(("queue_seconds", "fallback_calls"), [(300, 1), (330, 0)])
async def test_retryable_upstream_timeout_fallback_uses_remaining_overall_deadline(
    settings: Settings,
    hosted_gateway: HostedGateway,
    respx_mock: respx.MockRouter,
    elapsed: list[float],
    queue_seconds: float,
    fallback_calls: int,
) -> None:
    settings.resilience.max_retries = 0
    state = get_app_state(hosted_gateway.app)
    price = state.catalog.find("nvidia", "moonshotai/kimi-k3", "chat")
    assert price is not None
    price.fallbacks = ["groq/openai/gpt-oss-20b"]

    def timeout(request: httpx.Request) -> httpx.Response:
        elapsed[0] = queue_seconds
        return httpx.Response(504)

    primary = respx_mock.post("https://nvidia.test/v1/chat/completions").mock(side_effect=timeout)
    fallback = respx_mock.post("https://groq.test/v1/chat/completions").respond(
        200, json=hosted_completion("openai/gpt-oss-20b")
    )

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)

    assert primary.call_count == 1
    assert fallback.call_count == fallback_calls
    assert response.status_code == (200 if fallback_calls else 504)


async def test_fallback_cannot_reset_deadline_after_a_queued_upstream_timeout(
    settings: Settings,
    hosted_gateway: HostedGateway,
    respx_mock: respx.MockRouter,
    elapsed: list[float],
) -> None:
    settings.resilience.max_retries = 0
    state = get_app_state(hosted_gateway.app)
    price = state.catalog.find("nvidia", "moonshotai/kimi-k3", "chat")
    assert price is not None
    price.fallbacks = ["groq/openai/gpt-oss-20b"]
    cancelled = asyncio.Event()

    def timeout(request: httpx.Request) -> httpx.Response:
        elapsed[0] = 329.9
        return httpx.Response(504)

    async def stalled(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    primary = respx_mock.post("https://nvidia.test/v1/chat/completions").mock(side_effect=timeout)
    respx_mock.post("https://groq.test/v1/chat/completions").mock(side_effect=stalled)

    response = await asyncio.wait_for(
        hosted_gateway.client.post("/v1/chat/completions", json=CHAT), 5
    )

    assert response.status_code == 504
    assert primary.call_count == 1
    assert cancelled.is_set()


async def test_slow_first_chunk_uses_nvidia_read_timeout_and_extended_request_deadline(
    hosted_gateway: HostedGateway,
    respx_mock: respx.MockRouter,
    elapsed: list[float],
) -> None:
    waiting, release = asyncio.Event(), asyncio.Event()

    async def slow_first_chunk() -> AsyncIterator[bytes]:
        waiting.set()
        await release.wait()
        elapsed[0] = 180.7
        for chunk in sse(*hosted_stream("moonshotai/kimi-k3"), "[DONE]"):
            yield chunk

    route = respx_mock.post("https://nvidia.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=slow_first_chunk())
    )
    async with asyncio.TaskGroup() as tasks:
        pending = tasks.create_task(
            hosted_gateway.client.post(
                "/v1/chat/completions",
                json={**CHAT, "stream": True, "stream_options": {"include_usage": True}},
            )
        )
        await asyncio.wait_for(waiting.wait(), 5)
        assert not pending.done()
        assert route.calls.last.request.extensions["timeout"]["read"] == 300
        release.set()
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    response = pending.result()
    assert response.status_code == 200
    events = parse_events(response.text)
    assert events[-1] == "[DONE]"
    assert events[-2]["usage"]["completion_tokens_details"]["reasoning_tokens"] == 3
    assert hosted_gateway.records[0].ttfb_ms == 180700
