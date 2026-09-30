"""Exercise the production Lua decision with a simulated shared Redis clock."""

import math
import random
import uuid
from collections import deque
from collections.abc import Callable
from importlib.resources import files
from typing import Protocol, cast

import pytest
from redis.asyncio import Redis

from llm_gateway.limits.service import LimitService

pytestmark = pytest.mark.redis


class _RedisClock(Protocol):
    # redis-py's TIME stub leaves kwargs untyped; the actual result is two integers.
    async def time(self) -> tuple[int, int]: ...


@pytest.mark.parametrize(("rpm", "burst"), [(10, 1), (60, 3), (600, 30), (600, 100)])
async def test_every_rolling_minute_respects_rpm_plus_burst(
    test_redis: Redis, monkeypatch: pytest.MonkeyPatch, rpm: int, burst: int
) -> None:
    clock = [120.0]
    service = LimitService(test_redis, rpm_burst=burst, clock=lambda: clock[0])
    await _simulate_clock(service, test_redis, monkeypatch, lambda: clock[0])
    rng = random.Random(120600 + burst)  # noqa: S311 -- reproducible arrival generation, not secrets
    # Saturated minute boundaries expose the former weighted-counter over-admission.
    arrivals = [120 + i / 50 for i in range(12000)]
    arrivals += [rng.uniform(120, 360) for _ in range(rpm * 3)]
    arrivals += [float(t) for t in (120, 179, 180, 239, 240) for _ in range(burst * 3)]
    traces = [[179.0] * rpm + [180 + i / 50 for i in range(12000)], sorted(arrivals)]
    for trace in traces:
        admitted: deque[float] = deque()
        team = str(uuid.uuid4())
        for now in trace:
            clock[0] = now
            if (await service.window(team, "requests", rpm, 1))[0]:
                while admitted and admitted[0] <= now - 60:
                    admitted.popleft()
                admitted.append(now)
                assert len(admitted) <= rpm + burst


async def test_default_burst_and_next_slot_headers(
    test_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [120.0]
    service = LimitService(test_redis)
    await _simulate_clock(service, test_redis, monkeypatch, lambda: clock[0])
    team = str(uuid.uuid4())
    rows = [await service.window(team, "requests", 600, 1) for _ in range(30)]

    assert all(row[0] == 1 for row in rows)
    assert rows[0][1] == math.ceil(600 * 0.05) - 1
    assert (await service.window(team, "requests", 600, 1))[:3] == [0, 0, 1]
    clock[0] += 0.1
    assert (await service.window(team, "requests", 600, 1))[:3] == [1, 0, 1]


async def test_python_clock_skew_does_not_change_redis_admission_time(test_redis: Redis) -> None:
    service = LimitService(test_redis, clock=lambda: -1000000)
    team = str(uuid.uuid4())
    seconds, micros = await cast(_RedisClock, test_redis).time()

    result = await service.window(team, "requests", 1, 1)

    assert result[:3] == [1, 0, 60]
    assert result[3] >= seconds * 1000000 + micros
    assert await test_redis.pttl(f"lgw:requests:{team}:tat") > 0


async def test_gcra_sha_reload_and_check_only_do_not_spend_slots(test_redis: Redis) -> None:
    service = LimitService(test_redis, rpm_burst=1)
    service.scripts.shas["gcra"] = "0" * 40
    team = str(uuid.uuid4())

    assert (await service.window(team, "requests", 1, 0, False))[:3] == [1, 1, 0]
    assert (await service.window(team, "requests", 1, 1))[:3] == [1, 0, 60]
    assert (await service.window(team, "requests", 1, 1))[:3] == [0, 0, 60]


async def _simulate_clock(
    service: LimitService,
    client: Redis,
    monkeypatch: pytest.MonkeyPatch,
    clock: Callable[[], float],
) -> None:
    source = files("llm_gateway.limits").joinpath("scripts", "gcra.lua").read_text()
    source = source.replace("local clock = redis.call('TIME')", "local clock = {ARGV[4], 0}")
    # Real TTL time must not expire state while simulated time is frozen or jumping.
    source = source.replace("math.ceil((tat - now) * 1000)", "600000")
    sha = await client.script_load(source)
    original = service.scripts.call

    async def simulated(
        name: str, keys: list[str], args: list[str | int | float]
    ) -> list[int] | int:
        if name == "gcra":
            service.scripts.shas[name] = sha
            args = [*args, clock()]
        return await original(name, keys, args)

    monkeypatch.setattr(service.scripts, "call", simulated)
