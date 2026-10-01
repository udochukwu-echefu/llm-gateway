"""Both CLI and callable seeder verify the actual bound database before I/O."""

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class DemoSeedError(ValueError):
    """Only intentionally safe messages may be printed by the seeder CLI."""


def require_local_database(value: str | URL, *, allow_remote_demo: bool = False) -> None:
    try:
        url = make_url(value)
    except Exception as exc:
        raise DemoSeedError("Refusing demo seed: invalid database configuration.") from exc
    if url.drivername == "postgresql+asyncpg" and url.host and allow_remote_demo:
        return
    if url.drivername != "postgresql+asyncpg" or url.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "postgres",
    }:
        raise DemoSeedError("Refusing demo seed: database host must be local.")


def require_local_sessions(
    sessions: async_sessionmaker[AsyncSession], *, allow_remote_demo: bool = False
) -> None:
    engine = sessions.kw.get("bind")
    if not isinstance(engine, AsyncEngine):
        raise DemoSeedError("Refusing demo seed: cannot verify the database host.")
    require_local_database(engine.url, allow_remote_demo=allow_remote_demo)
