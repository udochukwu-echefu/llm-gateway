"""Real-Redis boundaries; IDs are unique, so no test touches another test's keys."""

import asyncio
import math
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis

from llm_gateway.errors import GatewayError
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.service import LimitService, month_end, picos
from tests.usage.test_writer import sample_record

pytestmark = pytest.mark.redis


def limits(
    *, rpm: int = 0, tpm: int = 0, concurrency: int = 0, budget: str = "0"
) -> EffectiveLimits:
    return EffectiveLimits(rpm, tpm, concurrency, Decimal(budget), Decimal("0.8"))


async def test_two_replicas_admit_exactly_ten_of_fifty_rpm(test_redis: Redis) -> None:
    team = uuid.uuid4()
    first, second = LimitService(test_redis), LimitService(test_redis)

    async def one(index: int) -> bool:
        try:
            lease, _ = await (first if index % 2 else second).admission(team, limits(rpm=10))
            await first.finish(team, lease, None, limits(rpm=10))
            return True
        except GatewayError:
            return False

    results = await asyncio.gather(*(one(i) for i in range(50)))

    assert results.count(True) == 10
    assert results.count(False) == 40


async def test_two_replicas_admit_only_three_while_leases_are_held(test_redis: Redis) -> None:
    team = uuid.uuid4()
    first, second = LimitService(test_redis), LimitService(test_redis)
    admitted: list[str | None] = []

    async def one(index: int) -> bool:
        try:
            lease, _ = await (first if index % 2 else second).admission(team, limits(concurrency=3))
            admitted.append(lease)
            return True
        except GatewayError:
            return False

    results = await asyncio.gather(*(one(i) for i in range(50)))

    assert results.count(True) == 3
    assert results.count(False) == 47
    for lease in admitted:
        await first.finish(team, lease, None, limits(concurrency=3))


async def test_budget_boundary_is_atomic_across_replicas(test_redis: Redis) -> None:
    team = uuid.uuid4()
    now = datetime.now(UTC)
    key = f"lgw:budget:{team}:{now:%Y-%m}"
    await test_redis.set(key, picos(Decimal("0.999999999999")), ex=120)
    first, second = LimitService(test_redis), LimitService(test_redis)
    # The boundary is checked concurrently; neither replica can change a check result.
    results = await asyncio.gather(
        *(
            (first if i % 2 else second).check_budget(team, limits(budget="1"), now)
            for i in range(50)
        )
    )
    assert all(row[0] == 1 for row in results)
    await test_redis.incrby(key, 1)
    blocked = await asyncio.gather(
        *(
            (first if i % 2 else second).check_budget(team, limits(budget="1"), now)
            for i in range(50)
        )
    )
    assert all(row[0] == 0 for row in blocked)


async def test_budget_retry_after_rounds_up_to_next_utc_month(test_redis: Redis) -> None:
    team = uuid.uuid4()
    now = datetime(2026, 9, 30, 23, 59, 59, 200000, tzinfo=UTC)
    await test_redis.set(f"lgw:budget:{team}:2026-09", picos(Decimal("1")), ex=120)
    service = LimitService(test_redis, clock=now.timestamp)

    with pytest.raises(GatewayError) as failure:
        await service.admission(team, limits(budget="1"))

    assert failure.value.type == "insufficient_quota"
    assert failure.value.code == "budget_exceeded"
    assert "2026-09" in failure.value.message
    assert failure.value.headers["Retry-After"] == "1"
    assert failure.value.headers["x-ratelimit-limit-requests"] == "0"


async def test_sliding_window_weights_previous_at_edge(test_redis: Redis) -> None:
    team = str(uuid.uuid4())
    clock = [120.0]
    service = LimitService(test_redis, clock=lambda: clock[0])
    for _ in range(10):
        assert (await service.window(team, "requests", 10, 1))[0] == 1
    assert (await service.window(team, "requests", 10, 1))[0] == 0
    clock[0] = 210.0
    assert (await service.window(team, "requests", 10, 1)) == [1, 4, 30]
    clock[0] = 240.0
    assert (await service.window(team, "requests", 10, 1))[0] == 1


async def test_missing_script_sha_is_reloaded_without_losing_admission(test_redis: Redis) -> None:
    service = LimitService(test_redis)
    service.scripts.shas["window"] = "0" * 40

    result = await service.window(str(uuid.uuid4()), "requests", 1, 1)

    assert result[0] == 1
    assert service.scripts.shas["window"] != "0" * 40


async def test_lease_expires_after_crash(test_redis: Redis) -> None:
    team = uuid.uuid4()
    clock = [1000.0]
    service = LimitService(test_redis, lease_ttl=2, clock=lambda: clock[0])
    await service.admission(team, limits(concurrency=1))
    with pytest.raises(GatewayError, match="concurrency"):
        await service.admission(team, limits(concurrency=1))
    clock[0] += 3
    lease, _ = await service.admission(team, limits(concurrency=1))
    assert lease is not None


async def test_active_stream_renews_lease_beyond_original_ttl(test_redis: Redis) -> None:
    team = uuid.uuid4()
    service = LimitService(test_redis, lease_ttl=2)
    lease, _ = await service.admission(team, limits(concurrency=1))
    assert lease is not None
    heartbeat = asyncio.create_task(service.keep_lease_alive(team, lease))
    try:
        await asyncio.sleep(2.5)
        with pytest.raises(GatewayError, match="concurrency"):
            await service.admission(team, limits(concurrency=1))
    finally:
        heartbeat.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat
        await service.finish(team, lease, None, limits(concurrency=1))

    new_lease, _ = await service.admission(team, limits(concurrency=1))
    assert new_lease is not None


async def test_tpm_uses_recorded_tokens_and_two_inflight_calls_can_overshoot(
    test_redis: Redis,
) -> None:
    team = uuid.uuid4()
    service = LimitService(test_redis)
    configured = limits(tpm=10, concurrency=2)

    leases = [await service.admission(team, configured) for _ in range(2)]
    receipt = replace(
        sample_record(),
        team_id=team,
        prompt_tokens=9,
        completion_tokens=1,
        cost_status="not_billed",
        cost_usd=Decimal(0),
    )
    for lease, _ in leases:
        await service.finish(team, lease, receipt, configured)

    assert (await service.window(str(team), "tokens", 10, 0, False))[0] == 0
    with pytest.raises(GatewayError) as failure:
        await service.admission(team, configured)
    assert failure.value.code == "rate_limit_exceeded"


async def test_budget_alert_is_deduplicated_and_unknown_cost_is_not_added(
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team = uuid.uuid4()
    service = LimitService(test_redis)
    configured = limits(budget="1")
    key = f"lgw:budget:{team}:{datetime.now(UTC):%Y-%m}"
    await test_redis.set(key, 0, ex=120)
    warnings: list[str] = []

    def capture_warning(name: str, **fields: object) -> None:
        warnings.append(name)

    monkeypatch.setattr("llm_gateway.limits.service.log.warning", capture_warning)
    receipt = replace(
        sample_record(), team_id=team, cost_status="priced", cost_usd=Decimal("0.400000000001")
    )

    await service.finish(team, None, receipt, configured)
    await service.finish(team, None, receipt, configured)
    await service.finish(
        team, None, replace(receipt, cost_usd=None, cost_status="stream_incomplete"), configured
    )

    assert warnings == ["budget_alert"]
    assert int(await test_redis.get(key)) == picos(Decimal("0.800000000002"))


async def test_pico_dollars_remain_exact_above_float_precision(test_redis: Redis) -> None:
    assert picos(Decimal("9008.000000000001")) == 9008000000000001
    team = uuid.uuid4()
    now = datetime.now(UTC)
    key = f"lgw:budget:{team}:{now:%Y-%m}"
    budget = Decimal("9008.000000000001")
    await test_redis.set(key, picos(budget) - 1, ex=120)
    service = LimitService(test_redis)
    assert (await service.check_budget(team, limits(budget=str(budget)), now))[0] == 1
    await test_redis.incrby(key, 1)
    assert (await service.check_budget(team, limits(budget=str(budget)), now))[0] == 0
    assert math.ceil((month_end(now) - now).total_seconds()) > 0


@pytest.mark.parametrize(("mode", "expected"), [("open", True), ("closed", False)])
async def test_redis_failure_obeys_fail_mode(
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: bool,
) -> None:
    service = LimitService(test_redis, fail_mode=mode)

    async def broken(*args: object) -> None:
        raise ConnectionError("simulated Redis failure")

    monkeypatch.setattr(service.scripts, "call", broken)

    if expected:
        lease, _ = await service.admission(uuid.uuid4(), limits(rpm=1))
        assert lease is None
    else:
        with pytest.raises(GatewayError) as failure:
            await service.admission(uuid.uuid4(), limits(rpm=1))
        assert failure.value.status_code == 503
        assert failure.value.code == "limits_unavailable"
