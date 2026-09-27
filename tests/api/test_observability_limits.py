import time
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest
from redis.asyncio import Redis

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository

pytestmark = pytest.mark.redis


@pytest.mark.parametrize("kind", ["requests", "tokens", "concurrency", "budget", "auth_ip"])
async def test_each_limit_rejection_moves_its_metric(
    kind: str,
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record,
        limits=LimitOverrides(rpm=1, tpm=1, max_concurrency=1, monthly_budget_usd=Decimal(1)),
    )
    service = LimitService(test_redis)
    now = time.time()
    slot = int(now // 60)
    subject = str(record.team_id)
    client_ip = "192.0.2.123"
    await test_redis.delete(*(f"lgw:auth-fail:{client_ip}:{slot - i}" for i in (0, 1)))
    if kind in {"requests", "tokens"}:
        await test_redis.set(f"lgw:{kind}:{subject}:{slot}", 1, ex=120)
    elif kind == "concurrency":
        await test_redis.zadd(f"lgw:leases:{subject}", {"existing": now + 60})
        await test_redis.expire(f"lgw:leases:{subject}", 120)
    elif kind == "budget":
        await test_redis.set(
            f"lgw:budget:{subject}:{time.strftime('%Y-%m', time.gmtime(now))}", 10**12, ex=120
        )
    else:
        await test_redis.set(f"lgw:auth-fail:{client_ip}:{slot}", 20, ex=120)
    app = create_app(
        settings, key_repository=memory_repository, catalog=test_catalog, limit_service=service
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(client_ip, 1234)),
            base_url="http://gateway.test",
        ) as client,
    ):
        response = await client.get(
            "/v1/models", headers={"authorization": f"Bearer {issued_test_key}"}
        )

    assert response.status_code == 429
    assert service.metrics is not None
    assert service.metrics.registry.get_sample_value("lgw_rate_limited_total", {"kind": kind}) == 1
    await test_redis.delete(*(f"lgw:auth-fail:{client_ip}:{slot - i}" for i in (0, 1)))
