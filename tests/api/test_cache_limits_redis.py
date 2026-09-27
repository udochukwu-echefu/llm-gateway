"""A paid miss can exhaust limits without blocking its later free hit."""

import base64
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import SecretStr
from redis.asyncio import Redis

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.service import ResponseCache
from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.gateway_state import get_app_state
from llm_gateway.limits.configuration import LimitOverrides, resolve
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository
from tests.fixtures import EMBEDDINGS

pytestmark = pytest.mark.redis


@pytest.fixture
async def limited_cache_client(
    test_redis: Redis,
    settings: Settings,
    test_catalog: Catalog,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
) -> AsyncIterator[tuple[httpx.AsyncClient, LimitService, MemoryKeyRepository]]:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record,
        limits=LimitOverrides(
            rpm=2,
            tpm=1,
            max_concurrency=1,
            monthly_budget_usd=Decimal("0.000000000001"),
        ),
    )
    service = LimitService(test_redis)
    app = create_app(
        settings, key_repository=memory_repository, catalog=test_catalog, limit_service=service
    )
    async with app.router.lifespan_context(app):
        state = get_app_state(app)
        app.state.gateway = replace(
            state,
            response_cache=ResponseCache(
                test_redis, CacheCipher(SecretStr(base64.b64encode(b"r" * 32).decode()))
            ),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client:
            yield client, service, memory_repository


async def test_hit_is_served_when_budget_and_tpm_are_exceeded(
    limited_cache_client: tuple[httpx.AsyncClient, LimitService, MemoryKeyRepository],
    upstream: respx.MockRouter,
    settings: Settings,
) -> None:
    client, service, repository = limited_cache_client
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/embedding", "input": "same"}
    record = next(iter(repository.records.values()))
    limits = resolve(record.limits, settings.limits)

    first = await client.post("/v1/embeddings", json=body)
    budget = await service.check_budget(record.team_id, limits, datetime.now(UTC))
    second = await client.post("/v1/embeddings", json=body)

    assert first.status_code == 200
    assert budget[0] == 0
    assert second.status_code == 200
    assert second.headers["x-lgw-cache"] == "hit"
    assert second.headers["x-ratelimit-remaining-requests"] == "0"
    assert route.call_count == 1
