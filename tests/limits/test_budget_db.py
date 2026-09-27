"""Rebuild missing monthly spend from durable receipts, not an invented zero."""

import asyncio
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.service import LimitService, picos
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.repository import PostgresUsageRepository
from tests.usage.test_writer import sample_record

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def test_missing_budget_is_rebuilt_once_from_postgres(
    migrated_database: str,
    test_redis: Redis,
) -> None:
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repository = PostgresUsageRepository(sessions)
    now = datetime.now(UTC)
    async with sessions.begin() as session:
        org = Organization(name=f"budget-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        team = Team(organization_id=org.id, name="budget")
        session.add(team)
        await session.flush()
        record = replace(
            sample_record(),
            organization_id=org.id,
            team_id=team.id,
            created_at=now,
            cost_usd=Decimal("0.750000000001"),
        )
        team_id = team.id
    await repository.insert([record])
    limits = EffectiveLimits(0, 0, 0, Decimal("1"), Decimal("0.8"))
    calls = 0

    async def counted_total(team: uuid.UUID, start: datetime, end: datetime) -> Decimal:
        nonlocal calls
        calls += 1
        return await repository.month_spend(team, start, end)

    first = LimitService(test_redis, spend_total=counted_total)
    second = LimitService(test_redis, spend_total=counted_total)
    try:
        results = await asyncio.gather(
            *((first if i % 2 else second).check_budget(team_id, limits, now) for i in range(20))
        )
        stored = await test_redis.get(f"lgw:budget:{team_id}:{now:%Y-%m}")

        assert calls == 1
        assert all(row[0] == 1 for row in results)
        assert stored is not None
        assert int(stored) == picos(Decimal("0.750000000001"))
    finally:
        await engine.dispose()
