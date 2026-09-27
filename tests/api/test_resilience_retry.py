import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, STREAM, parse_events, sse

pytestmark = pytest.mark.respx(assert_all_called=False)


@pytest.mark.parametrize(
    ("failure", "calls"),
    [
        (httpx.ConnectError("refused"), 3),
        (httpx.ConnectTimeout("connect"), 3),
        (httpx.PoolTimeout("pool"), 3),
        (httpx.ReadTimeout("read"), 1),
        (httpx.WriteTimeout("write"), 1),
        (httpx.ReadError("read"), 1),
        (429, 3),
        (500, 3),
        (502, 3),
        (503, 3),
        (504, 3),
        (529, 3),
        (400, 1),
        (401, 1),
        (403, 1),
        (404, 1),
        (408, 1),
        (413, 1),
        (422, 1),
        (501, 1),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
async def test_retry_table_counts_provider_calls(
    resilient: ResilientApp,
    failure: httpx.HTTPError | int,
    calls: int,
    stream: bool,
) -> None:
    route = resilient.router.post("https://groq.test/v1/chat/completions")
    if isinstance(failure, int):
        route.respond(failure)
    else:
        route.mock(side_effect=failure)

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": stream}
    )

    assert response.status_code >= 400
    assert route.call_count == calls
    assert (response.headers.get("x-lgw-attempts")) == (str(calls) if calls > 1 else None)


async def test_read_timeout_retries_only_when_enabled(resilient: ResilientApp) -> None:
    resilient.service.settings.retry_read_timeouts = True
    route = resilient.router.post("https://groq.test/v1/chat/completions").mock(
        side_effect=[httpx.ReadTimeout("read"), httpx.Response(200, json=COMPLETION)]
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    assert route.call_count == 2
    assert resilient.time.delays == [0.125]


async def test_no_retry_or_fallback_after_first_streamed_byte(resilient: ResilientApp) -> None:
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield sse(STREAM[0])[0]
            raise httpx.ReadTimeout("after first chunk")

    resilient.service.settings.retry_read_timeouts = True
    resilient.fallbacks("deepseek/model")

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Broken())

    route = resilient.router.post("https://groq.test/v1/chat/completions").mock(side_effect=broken)
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    )

    events = parse_events(response.text)
    assert events[0]["choices"][0]["delta"]["content"] == "h"
    assert events[-1]["error"]["code"] == "upstream_timeout"
    assert route.call_count == 1
    assert fallback.call_count == 0
    assert "[DONE]" not in response.text


@pytest.mark.parametrize(("retry_after", "calls", "delays"), [("1", 3, [1, 1]), ("3", 1, [])])
async def test_retry_after_waits_or_falls_back(
    resilient: ResilientApp,
    retry_after: str,
    calls: int,
    delays: list[float],
) -> None:
    resilient.fallbacks("deepseek/model")
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        503, headers={"retry-after": retry_after}
    )
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    assert primary.call_count == calls
    assert fallback.call_count == 1
    assert resilient.time.delays == delays


async def test_deadline_cancels_inflight_attempt_without_fallback(resilient: ResilientApp) -> None:
    cancelled = asyncio.Event()
    started: list[str] = []

    async def stalled(request: httpx.Request) -> httpx.Response:
        started.append(request.url.host)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200, json=COMPLETION)

    resilient.service.settings.deadline_s = 0.02
    resilient.fallbacks("deepseek/model")
    resilient.router.post("https://groq.test/v1/chat/completions").mock(side_effect=stalled)
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 504
    assert cancelled.is_set()
    assert started == ["groq.test"]
    assert fallback.call_count == 0


async def test_shared_deadline_limits_retries_and_fallback(resilient: ResilientApp) -> None:
    resilient.service.settings.deadline_s = 0.2
    resilient.fallbacks("deepseek/model")
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(503)

    started: list[str] = []

    async def slow_fallback(request: httpx.Request) -> httpx.Response:
        started.append(request.url.host)
        await asyncio.sleep(0.09)
        return httpx.Response(200, json=COMPLETION)

    resilient.router.post("https://deepseek.test/v1/chat/completions").mock(
        side_effect=slow_fallback
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 504
    assert primary.call_count == 2
    assert started == ["deepseek.test"]
    assert resilient.time.delays == [0.125]


async def test_http_retry_budget_is_strict_and_recovers(resilient: ResilientApp) -> None:
    budget = resilient.service.budgets["groq"]
    budget.firsts.clear()
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    resilient.service.settings.breaker_min_calls = 100
    for _ in range(5):
        await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    assert route.call_count == 6
    assert len(resilient.time.delays) == 1
    resilient.time.now = 60
    route.respond(200, json=COMPLETION)
    for _ in range(4):
        await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    route.mock(side_effect=[httpx.Response(503), httpx.Response(200, json=COMPLETION)])

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    assert response.headers["x-lgw-attempts"] == "2"
