"""Inspect pool policy without opening sockets; production pooling remains unchanged."""

from unittest.mock import Mock

import pytest
from redis.asyncio.connection import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from llm_gateway.storage_connections import database_engine, redis_connection


async def test_demo_postgres_retains_no_idle_connections() -> None:
    engine = database_engine("postgresql+asyncpg://fake:fake@fake.invalid/fake", demo=True)
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        await engine.dispose()


async def test_production_postgres_keeps_pool_and_checkout_pre_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock(wraps=create_async_engine)
    monkeypatch.setattr("llm_gateway.storage_connections.create_async_engine", factory)
    engine = database_engine("postgresql+asyncpg://fake:fake@fake.invalid/fake")
    try:
        assert isinstance(engine.pool, AsyncAdaptedQueuePool)
        factory.assert_called_once_with(
            "postgresql+asyncpg://fake:fake@fake.invalid/fake", pool_pre_ping=True
        )
    finally:
        await engine.dispose()


async def test_demo_redis_disables_health_checks_and_tcp_keepalive_even_in_url() -> None:
    client = redis_connection(
        "redis://fake.invalid/0?socket_keepalive=true&health_check_interval=1", 0.05, demo=True
    )
    try:
        connection = client.connection_pool.make_connection()
        assert isinstance(connection, Connection)
        assert connection.socket_keepalive is False
        assert connection.health_check_interval == 0
    finally:
        await client.aclose()


async def test_production_redis_preserves_url_options() -> None:
    client = redis_connection(
        "redis://fake.invalid/0?socket_keepalive=true&health_check_interval=1", 0.05
    )
    try:
        connection = client.connection_pool.make_connection()
        assert isinstance(connection, Connection)
        assert connection.socket_keepalive is True
        assert connection.health_check_interval == 1
    finally:
        await client.aclose()
