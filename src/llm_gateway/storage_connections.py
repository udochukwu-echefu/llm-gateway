"""Demo storage must not leave Postgres keepalive sockets or Redis health probes behind."""

from typing import cast

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


def database_engine(url: str, *, demo: bool = False) -> AsyncEngine:
    if demo:
        # No idle asyncpg sockets (including kernel TCP keepalives). Reconnect on demand.
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(url, pool_pre_ping=True)


def redis_connection(url: str, timeout_s: float, *, demo: bool = False) -> Redis:
    client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis-py kwargs types
        url, socket_timeout=timeout_s, socket_connect_timeout=timeout_s
    )
    if demo:
        # URL query options take precedence over from_url kwargs; clamp after parsing.
        options = cast(dict[str, object], client.connection_pool.connection_kwargs)  # pyright: ignore[reportUnknownMemberType]  # redis-py kwargs values are untyped
        options.update(socket_keepalive=False, health_check_interval=0)
    return client
