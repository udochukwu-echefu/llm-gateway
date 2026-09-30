"""Admission holds and renews a lease while NVIDIA has not sent its first SSE chunk."""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
import respx
from redis.asyncio import Redis

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.gateway_state import get_app_state
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from tests.conftest import UPSTREAM_KEY, MemoryKeyRepository
from tests.fixtures import parse_events, sse
from tests.providers.fixtures import hosted_stream

pytestmark = pytest.mark.redis


async def test_lease_renews_before_slow_first_chunk_and_releases_after_stream(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(max_concurrency=1)
    )
    settings.providers = ProvidersSettings.model_validate(
        {
            "nvidia": {
                "api_key": UPSTREAM_KEY,
                "base_url": "https://nvidia.test/v1",
            }
        }
    )
    settings.resilience.deadline_s = 330
    service = LimitService(test_redis, lease_ttl=2)  # Accelerate renewal, not the production TTL.
    renewed, waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = service.scripts.call

    async def observe_renewal(
        name: str, keys: list[str], args: list[str | int | float]
    ) -> list[int] | int:
        result = await original(name, keys, args)
        if name == "renew" and result == 1:
            renewed.set()
        return result

    monkeypatch.setattr(service.scripts, "call", observe_renewal)
    app = create_app(settings, key_repository=memory_repository, limit_service=service)
    elapsed = [0.0]

    async def slow_first_chunk() -> AsyncIterator[bytes]:
        waiting.set()
        await release.wait()
        elapsed[0] = 180.7  # Simulate queue duration without making tests sleep for minutes.
        for chunk in sse(*hosted_stream("moonshotai/kimi-k3"), "[DONE]"):
            yield chunk

    route = respx_mock.post("https://nvidia.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, content=slow_first_chunk())
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        get_app_state(app).resilience.clock = lambda: elapsed[0]
        async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
            pending = tasks.create_task(
                client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "nvidia/moonshotai/kimi-k3",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    },
                )
            )
            await waiting.wait()
            await renewed.wait()
            assert not pending.done()
            assert await test_redis.zcount(f"lgw:leases:{record.team_id}", time.time(), "+inf") == 1
            assert route.calls.last.request.extensions["timeout"]["read"] == 300
            release.set()

    assert pending.result().status_code == 200
    assert parse_events(pending.result().text)[-1] == "[DONE]"
    assert await test_redis.zcard(f"lgw:leases:{record.team_id}") == 0
