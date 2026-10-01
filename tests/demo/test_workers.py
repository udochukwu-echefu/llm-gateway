import asyncio
import json
from typing import cast

import httpx
import pytest
import respx
from respx.models import Call

from scripts.demo_traffic import GATEWAY_URL, MODELS, run_traffic, send_traffic, traffic_payload


def test_traffic_mix_has_aliases_models_streams_and_synthetic_email() -> None:
    payloads = [traffic_payload(index) for index in range(20)]
    assert {payload["model"] for payload in payloads} == set(MODELS)
    assert any("/" not in str(payload["model"]) for payload in payloads)
    assert {payload["stream"] for payload in payloads} == {True, False}
    assert sum("@example.invalid" in json.dumps(payload) for payload in payloads) == 5


async def test_traffic_drains_response_without_logging_content(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(GATEWAY_URL).mock(
        return_value=httpx.Response(200, content=b"synthetic-body")
    )
    async with httpx.AsyncClient() as client:
        assert await send_traffic(client, "synthetic-tenant-placeholder", 0) == 200
    assert route.called
    request = cast(Call, route.calls[0]).request
    assert json.loads(request.content)["stream"] is True
    assert request.headers["Authorization"] == "Bearer synthetic-tenant-placeholder"


@pytest.mark.parametrize("fails", [False, True])
async def test_traffic_loop_stops_permanently_at_window_with_fake_clock(fails: bool) -> None:
    now = 1000.0
    starts: list[float] = []
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        nonlocal now
        delays.append(delay)
        now += delay

    def respond(request: httpx.Request) -> httpx.Response:
        starts.append(now - 1000)
        if fails:
            raise httpx.ConnectError("synthetic outage", request=request)
        return httpx.Response(200, content=b"synthetic-body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await run_traffic(
            client,
            "synthetic-placeholder",
            600,
            clock=lambda: now,
            sleep=sleep,
            jitter=lambda low, high: 60,
        )
        now += 3600  # Advancing the clock after return cannot resurrect the loop.

    assert starts[:3] == pytest.approx([0, 0.2, 0.4])
    assert starts[3:] == pytest.approx([60.4 + 60 * index for index in range(9)])
    assert sum(delays) == pytest.approx(600)
    assert len(starts) == 12
    assert all(start < 600 for start in starts)


async def test_slow_traffic_request_does_not_start_another_after_deadline() -> None:
    now = 0.0
    sleeps: list[float] = []
    calls = 0

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal now, calls
        calls += 1
        now += 21
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await run_traffic(client, "synthetic-placeholder", 10, clock=lambda: now, sleep=sleep)

    assert calls == 1
    assert sleeps == []


async def test_traffic_window_cancels_a_request_that_never_finishes() -> None:
    cancelled = asyncio.Event()
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await asyncio.wait_for(run_traffic(client, "synthetic-placeholder", 1), 5)

    assert cancelled.is_set()
    assert calls == 1
