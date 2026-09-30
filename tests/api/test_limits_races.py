"""Two independent app lifespans share only Redis and the fake team identity."""

import asyncio
from contextlib import AsyncExitStack
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx
from redis.asyncio import Redis

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService, picos
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION

pytestmark = pytest.mark.redis


async def replicas(
    stack: AsyncExitStack,
    redis: Redis,
    settings: Settings,
    repository: MemoryKeyRepository,
    catalog: Catalog,
    issued_key: str,
) -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    clients: list[httpx.AsyncClient] = []
    for _ in range(2):
        app = create_app(
            settings,
            key_repository=repository,
            catalog=catalog,
            limit_service=LimitService(redis, rpm_burst=10),
        )
        await stack.enter_async_context(app.router.lifespan_context(app))
        client = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gateway.test",
                headers={"authorization": f"Bearer {issued_key}"},
            )
        )
        clients.append(client)
    return clients[0], clients[1]


async def test_fifty_requests_across_two_app_instances_admit_exactly_ten(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(record, limits=LimitOverrides(rpm=10))
    upstream.post("/chat/completions").respond(200, json=COMPLETION)
    async with AsyncExitStack() as stack:
        clients = await replicas(
            stack, test_redis, settings, memory_repository, test_catalog, issued_test_key
        )
        results = await asyncio.gather(
            *(clients[i % 2].post("/v1/chat/completions", json=CHAT_REQUEST) for i in range(50))
        )

    assert sum(response.status_code == 200 for response in results) == 10
    assert sum(response.status_code == 429 for response in results) == 40


async def test_budget_boundary_blocks_fifty_requests_across_two_instances(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(monthly_budget_usd=Decimal("1"))
    )
    key = f"lgw:budget:{record.team_id}:{datetime.now(UTC):%Y-%m}"
    await test_redis.set(key, picos(Decimal("1")), ex=120)
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    async with AsyncExitStack() as stack:
        clients = await replicas(
            stack, test_redis, settings, memory_repository, test_catalog, issued_test_key
        )
        results = await asyncio.gather(
            *(clients[i % 2].post("/v1/chat/completions", json=CHAT_REQUEST) for i in range(50))
        )

    assert sum(response.status_code == 429 for response in results) == 50
    assert all(response.json()["error"]["code"] == "budget_exceeded" for response in results)
    assert all(int(response.headers["retry-after"]) > 0 for response in results)
    assert not route.called


async def test_concurrency_three_across_two_instances_admits_only_three(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(max_concurrency=3)
    )
    release = asyncio.Event()
    three_started = asyncio.Event()
    started = 0

    async def slow_provider(request: httpx.Request) -> httpx.Response:
        nonlocal started
        started += 1
        if started == 3:
            three_started.set()
        await release.wait()
        return httpx.Response(200, json=COMPLETION)

    upstream.post("/chat/completions").mock(side_effect=slow_provider)
    async with AsyncExitStack() as stack:
        clients = await replicas(
            stack, test_redis, settings, memory_repository, test_catalog, issued_test_key
        )
        tasks = [
            asyncio.create_task(clients[i % 2].post("/v1/chat/completions", json=CHAT_REQUEST))
            for i in range(50)
        ]
        try:
            await asyncio.wait_for(three_started.wait(), 5)
            await asyncio.sleep(0.1)
        finally:
            release.set()
        results = await asyncio.gather(*tasks)

    assert sum(response.status_code == 200 for response in results) == 3
    assert sum(response.status_code == 429 for response in results) == 47
