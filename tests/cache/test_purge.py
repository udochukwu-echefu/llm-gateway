"""Admin purge is scoped by database IDs, not operator-supplied glob patterns."""

import uuid

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llm_gateway.admin.cli import execute, parser
from llm_gateway.audit.models import AuditEvent
from llm_gateway.cache.purge import purge
from llm_gateway.tenants.repository import PostgresKeyRepository

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def test_purge_only_target_team_and_audit_with_scan(
    migrated_database: str,
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repo = PostgresKeyRepository(sessions, actor="cache-test")
    name = f"cache-org-{uuid.uuid4().hex}"
    org = await repo.create_org(name)
    target = await repo.create_team(name, "target")
    sibling = await repo.create_team(name, "sibling")
    outsider = await repo.create_org(f"other-{uuid.uuid4().hex}")
    other = await repo.create_team(outsider.name, "target")
    keys = [f"lgw:cache:{team.id}:hash" for team in (target, sibling, other)]
    await test_redis.mset({key: "encrypted" for key in keys})

    async def forbid_keys(pattern: str) -> list[bytes]:
        raise AssertionError("KEYS is forbidden")

    monkeypatch.setattr(test_redis, "keys", forbid_keys)
    try:
        args = parser().parse_args(["cache", "purge", name, "--team", "target"])
        result = await execute(args, repo, b"unused", cache_client=test_redis)

        assert result == "Purged 1 cache entries"
        assert await test_redis.get(keys[0]) is None
        assert await test_redis.get(keys[1]) == b"encrypted"
        assert await test_redis.get(keys[2]) == b"encrypted"
        async with sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(AuditEvent).where(AuditEvent.action == "cache-purge")
                    )
                ).all()
            )
        assert len(rows) == 1
        assert rows[0].target_type == "team"
        assert rows[0].target_id == str(target.id)
        assert await purge(repo, test_redis, name, None) == 1
        assert await test_redis.get(keys[2]) == b"encrypted"
        assert org.id is not None
    finally:
        await test_redis.delete(*keys)
        await engine.dispose()
