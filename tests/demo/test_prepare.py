"""Bounded boot helpers and migration serialization, without network or child commands."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from deploy.demo.prepare import (
    DEPENDENCY_WAIT_S,
    migrate,
    refresh_traffic_budget,
    wait_dependencies,
)
from llm_gateway.limits.configuration import LimitOverrides


async def test_migration_runs_only_under_lock_and_unlocks_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_DATABASE_URL", "synthetic-unused-url")
    connection = Mock(scalar=AsyncMock(return_value=True), execute=AsyncMock())
    context = Mock(
        __aenter__=AsyncMock(return_value=connection), __aexit__=AsyncMock(return_value=False)
    )
    engine = Mock(connect=Mock(return_value=context), dispose=AsyncMock())
    monkeypatch.setattr("deploy.demo.prepare.create_async_engine", Mock(return_value=engine))
    run = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr("deploy.demo.prepare.subprocess.run", run)

    with pytest.raises(RuntimeError, match="migration failed"):
        await migrate()

    assert "pg_try_advisory_lock" in str(connection.scalar.call_args.args[0])
    assert run.call_args.args[0][-2:] == ["upgrade", "head"]
    assert run.call_args.kwargs["timeout"] == 45
    assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])
    engine.dispose.assert_awaited_once()


def _dependencies(
    monkeypatch: pytest.MonkeyPatch, *, postgres_error: bool, ping: AsyncMock
) -> tuple[Mock, Mock, AsyncMock]:
    monkeypatch.setenv("GATEWAY_DATABASE_URL", "postgresql+asyncpg://user:secret@db.invalid/x")
    monkeypatch.setenv("GATEWAY_REDIS_URL", "redis://:secret@cache.invalid:6379")
    connection = Mock(execute=AsyncMock())
    context = Mock(
        __aenter__=AsyncMock(side_effect=OSError if postgres_error else None),
        __aexit__=AsyncMock(return_value=False),
    )
    context.__aenter__.return_value = connection
    engine = Mock(connect=Mock(return_value=context), dispose=AsyncMock())
    redis = Mock(ping=ping, aclose=AsyncMock())
    sleep = AsyncMock()
    monkeypatch.setattr("deploy.demo.prepare.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("deploy.demo.prepare.Redis", Mock(from_url=Mock(return_value=redis)))
    monkeypatch.setattr("deploy.demo.prepare.asyncio.sleep", sleep)
    return engine, redis, sleep


async def test_dependency_wait_has_bounded_timeout_and_closes_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, redis, _ = _dependencies(monkeypatch, postgres_error=True, ping=AsyncMock())
    monkeypatch.setattr("deploy.demo.prepare.time", Mock(monotonic=Mock(side_effect=[0, 0, 61])))

    with pytest.raises(RuntimeError, match="unavailable: Postgres"):
        await wait_dependencies()

    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_dependency_wait_stays_inside_the_supervisor_bound() -> None:
    # The supervisor kills the whole prepare stage at 90 s; migration and seeding need room.
    assert 30 < DEPENDENCY_WAIT_S <= 60


async def test_dependency_timeout_names_the_service_without_its_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _dependencies(monkeypatch, postgres_error=False, ping=AsyncMock(side_effect=OSError))
    monkeypatch.setattr("deploy.demo.prepare.time", Mock(monotonic=Mock(side_effect=[0, 0, 61])))

    with pytest.raises(RuntimeError, match="unavailable: Redis"):
        await wait_dependencies()

    output = capsys.readouterr().out
    assert "Redis did not accept a connection within 60s." in output
    assert "secret" not in output
    assert "invalid" not in output


async def test_dependency_wait_backs_off_and_succeeds_when_redis_wakes_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ping = AsyncMock(side_effect=[OSError, OSError, OSError, OSError, OSError, True])
    engine, redis, sleep = _dependencies(monkeypatch, postgres_error=False, ping=ping)
    monkeypatch.setattr("deploy.demo.prepare.time", Mock(monotonic=Mock(return_value=0)))

    await wait_dependencies()

    assert [call.args[0] for call in sleep.await_args_list] == [0.2, 0.4, 0.8, 1.6, 2.0]
    assert ping.await_count == 6
    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()


def _budget_admin(budget: Decimal | None) -> Mock:
    return Mock(
        team_limits=AsyncMock(
            return_value=(uuid.uuid4(), LimitOverrides(rpm=5, monthly_budget_usd=budget))
        ),
        set_limits=AsyncMock(),
    )


def _spend_sessions(spend: Decimal | None) -> Mock:
    session = Mock(scalar=AsyncMock(return_value=spend))
    return Mock(
        return_value=Mock(
            __aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=False)
        )
    )


NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


async def test_traffic_budget_is_raised_when_topped_up_spend_passes_it() -> None:
    # The live failure: a budget seeded in October, November spend already past it.
    admin = _budget_admin(Decimal("0.233947058824"))

    await refresh_traffic_budget(admin, _spend_sessions(Decimal("1.89")), NOW)

    admin.set_limits.assert_awaited_once_with(
        "Demo Co", "Support", budget=Decimal("2.223529411765")
    )


async def test_traffic_budget_is_left_alone_while_it_has_headroom() -> None:
    admin = _budget_admin(Decimal("2.22"))

    await refresh_traffic_budget(admin, _spend_sessions(Decimal("1.89")), NOW)

    admin.set_limits.assert_not_awaited()


@pytest.mark.parametrize(("budget", "spend"), [(None, Decimal("5")), (Decimal("1"), None)])
async def test_traffic_budget_needs_a_budget_and_spend_to_act(
    budget: Decimal | None, spend: Decimal | None
) -> None:
    admin = _budget_admin(budget)

    await refresh_traffic_budget(admin, _spend_sessions(spend), NOW)

    admin.set_limits.assert_not_awaited()
