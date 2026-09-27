import asyncio

from llm_gateway.resilience.breaker import CircuitBreaker
from llm_gateway.resilience.configuration import ResilienceSettings


def test_breaker_minimum_window_and_state_machine() -> None:
    now = [0.0]
    breaker = CircuitBreaker("groq", ResilienceSettings(), lambda: now[0])
    for _ in range(9):
        permit = breaker.acquire()
        assert permit is not None
        breaker.finish(permit, True)
    assert breaker.state == "closed"
    now[0] = 30
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, True)
    assert breaker.state == "closed"
    for _ in range(9):
        permit = breaker.acquire()
        assert permit is not None
        breaker.finish(permit, True)
    assert breaker.state == "open"
    assert breaker.acquire() is None
    now[0] += 30
    probe = breaker.acquire()
    assert probe is not None
    assert probe.probe
    assert breaker.state == "half_open"
    breaker.finish(probe, True)
    assert breaker.state == "open"
    now[0] += 30
    probe = breaker.acquire()
    assert probe is not None
    breaker.finish(probe, False)
    assert breaker.state == "closed"


async def test_exactly_one_half_open_probe_for_twenty_concurrent_calls() -> None:
    now = [0.0]
    breaker = CircuitBreaker("groq", ResilienceSettings(breaker_min_calls=1), lambda: now[0])
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, True)
    now[0] = 30
    release = asyncio.Event()
    admitted: list[bool] = []

    async def call() -> None:
        permit = breaker.acquire()
        admitted.append(permit is not None)
        await release.wait()
        if permit is not None:
            breaker.finish(permit, False)

    tasks = [asyncio.create_task(call()) for _ in range(20)]
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(*tasks)
    assert sum(admitted) == 1
    assert breaker.state == "closed"


def test_stale_completions_cannot_close_a_new_generation() -> None:
    now = [0.0]
    breaker = CircuitBreaker("groq", ResilienceSettings(breaker_min_calls=1), lambda: now[0])
    old = breaker.acquire()
    failed = breaker.acquire()
    assert old is not None
    assert failed is not None
    breaker.finish(failed, True)
    now[0] = 30
    probe = breaker.acquire()
    assert probe is not None
    breaker.finish(old, False)
    assert breaker.state == "half_open"
    breaker.abandon(probe)
    assert breaker.state == "open"


def test_half_failures_opens_at_ten_calls_and_logs_each_transition() -> None:
    from structlog.testing import capture_logs

    now = [0.0]
    breaker = CircuitBreaker("groq", ResilienceSettings(), lambda: now[0])
    with capture_logs() as logs:
        for failed in [False] * 5 + [True] * 5:
            permit = breaker.acquire()
            assert permit is not None
            breaker.finish(permit, failed)
        assert breaker.state == "open"
        now[0] = 30
        probe = breaker.acquire()
        assert probe is not None
        breaker.finish(probe, False)

    assert [event["event"] for event in logs] == [
        "circuit_opened",
        "circuit_half_open",
        "circuit_closed",
    ]
    assert logs[0]["calls"] == 10
    assert logs[0]["failures"] == 5
    assert all(event["provider"] == "groq" for event in logs)
