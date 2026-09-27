from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from redis.asyncio import Redis

from llm_gateway.gateway_state import get_app_state
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.service import LimitService, picos
from llm_gateway.usage.record import UsageRecord
from tests.api.conftest import ResilientApp
from tests.conftest import OfflineLimitService
from tests.fixtures import CHAT_REQUEST, COMPLETION

pytestmark = pytest.mark.respx(assert_all_called=False)


class CountingLimits(OfflineLimitService):
    def __init__(self) -> None:
        super().__init__()
        self.acquired = 0
        self.released = 0
        self.receipts: list[UsageRecord] = []

    async def admission(
        self, team: UUID, limits: EffectiveLimits
    ) -> tuple[str | None, dict[str, str]]:
        self.acquired += 1
        return "one-lease", {}

    async def finish_records(
        self, team: UUID, lease: str | None, records: Sequence[UsageRecord], limits: EffectiveLimits
    ) -> None:
        self.released += int(lease is not None)
        self.receipts.extend(records)


async def test_two_failures_and_fallback_record_every_attempt_with_one_lease(
    resilient: ResilientApp,
) -> None:
    limits = CountingLimits()
    state = get_app_state(resilient.app)
    resilient.app.state.gateway = replace(state, limits=limits)
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.max_retries = 1
    primary = resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    fallback = resilient.router.post("https://deepseek.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    await state.usage_writer.stop()

    assert response.status_code == 200
    assert primary.call_count == 2
    assert fallback.call_count == 1
    assert (limits.acquired, limits.released) == (1, 1)
    assert limits.receipts == resilient.records
    assert [r.attempt for r in resilient.records] == [1, 2, 3]
    assert [r.fallback_from for r in resilient.records] == [None, None, CHAT_REQUEST["model"]]
    assert [r.status_code for r in resilient.records] == [502, 502, 200]
    assert [r.cost_status for r in resilient.records] == ["not_billed", "not_billed", "priced"]
    assert [r.cost_usd for r in resilient.records[:2]] == [Decimal(0), Decimal(0)]
    assert resilient.records[2].cost_usd == Decimal("0.000000975")
    assert {r.request_id for r in resilient.records} == {response.headers["x-request-id"]}


@pytest.mark.redis
async def test_all_attempt_tokens_and_costs_reach_redis(
    resilient: ResilientApp, test_redis: Redis
) -> None:
    service = LimitService(test_redis)
    state = get_app_state(resilient.app)
    resilient.app.state.gateway = replace(state, limits=service)
    resilient.fallbacks("deepseek/model")
    resilient.service.settings.max_retries = 1
    resilient.router.post("https://groq.test/v1/chat/completions").respond(503)
    resilient.router.post("https://deepseek.test/v1/chat/completions").respond(200, json=COMPLETION)

    await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    await state.usage_writer.stop()
    final = resilient.records[-1]
    key = f"lgw:budget:{final.team_id}:{final.created_at:%Y-%m}"
    assert int(await test_redis.get(key) or 0) == picos(final.cost_usd or Decimal(0))
    assert (await service.window(str(final.team_id), "tokens", 100, 0, False))[1] == 90
    assert await test_redis.zcard(f"lgw:leases:{final.team_id}") == 0

    # Known billed usage on any attempt is additive, not overwritten by the final receipt.
    records = [
        replace(final, attempt=i, prompt_tokens=i, completion_tokens=i, cost_usd=Decimal(i))
        for i in (1, 2, 3)
    ]
    await service.finish_records(
        final.team_id, None, records, EffectiveLimits(0, 0, 0, Decimal(0), Decimal("0.8"))
    )
    assert (await service.window(str(final.team_id), "tokens", 100, 0, False))[1] == 78
    assert int(await test_redis.get(key) or 0) == picos(Decimal(6) + (final.cost_usd or Decimal(0)))


async def test_attempt_timings_exclude_other_attempts_and_backoff(resilient: ResilientApp) -> None:
    import httpx

    calls = 0

    def reply(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        resilient.time.now += 0.01
        return httpx.Response(503) if calls == 1 else httpx.Response(200, json=COMPLETION)

    resilient.router.post("https://groq.test/v1/chat/completions").mock(side_effect=reply)

    await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    await get_app_state(resilient.app).usage_writer.stop()

    assert [record.duration_ms for record in resilient.records] == [10, 10]
    assert [record.ttfb_ms for record in resilient.records] == [None, 10]
