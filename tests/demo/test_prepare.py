"""Bounded boot helpers and migration serialization, without network or child commands."""

from unittest.mock import AsyncMock, Mock

import pytest

from deploy.demo.prepare import migrate, wait_dependencies


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


async def test_dependency_wait_has_bounded_timeout_and_closes_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_DATABASE_URL", "synthetic-unused-url")
    monkeypatch.setenv("GATEWAY_REDIS_URL", "synthetic-unused-url")
    context = Mock(
        __aenter__=AsyncMock(side_effect=OSError), __aexit__=AsyncMock(return_value=False)
    )
    engine = Mock(connect=Mock(return_value=context), dispose=AsyncMock())
    redis = Mock(ping=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr("deploy.demo.prepare.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("deploy.demo.prepare.Redis", Mock(from_url=Mock(return_value=redis)))
    monkeypatch.setattr("deploy.demo.prepare.time", Mock(monotonic=Mock(side_effect=[0, 0, 31])))
    monkeypatch.setattr("deploy.demo.prepare.asyncio.sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="dependencies unavailable"):
        await wait_dependencies()

    redis.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
