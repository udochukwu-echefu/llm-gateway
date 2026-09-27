from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis

from llm_gateway.gateway_state import get_app_state
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService
from llm_gateway.routing.policy import ModelPolicy
from tests.api.conftest import ResilientApp
from tests.conftest import MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION

pytestmark = pytest.mark.redis


async def test_denied_request_consumes_no_rpm_budget_or_lease(
    resilient: ResilientApp, test_redis: Redis, memory_repository: MemoryKeyRepository
) -> None:
    now = datetime.now(UTC)
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record,
        policy=ModelPolicy(("groq/*",)),
        limits=LimitOverrides(rpm=1, monthly_budget_usd=Decimal("1"), max_concurrency=1),
    )
    service = LimitService(test_redis)
    state = get_app_state(resilient.app)
    resilient.app.state.gateway = replace(state, limits=service)
    budget_key = f"lgw:budget:{record.team_id}:{now:%Y-%m}"
    await test_redis.set(budget_key, "123", ex=60)
    forbidden = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    denied = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "deepseek/model"}
    )

    assert denied.status_code == 403
    assert not forbidden.called
    assert await test_redis.get(budget_key) == b"123"
    assert await test_redis.exists(f"lgw:leases:{record.team_id}") == 0
    slot = int(service.clock() // 60)
    assert (
        await test_redis.exists(
            f"lgw:requests:{record.team_id}:{slot}",
            f"lgw:requests:{record.team_id}:{slot - 1}",
        )
        == 0
    )
