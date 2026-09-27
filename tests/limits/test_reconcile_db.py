"""Reconciliation uses real Postgres receipts and Redis counters."""

import asyncio
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.config import Settings
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.reconcile import BudgetReconciler
from llm_gateway.limits.service import LimitService, month_end, picos
from llm_gateway.main import create_app
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.record import UsageRecord
from llm_gateway.usage.repository import PostgresUsageRepository
from llm_gateway.usage.writer import UsageWriter
from tests.tenants.support import DatabaseTestStore
from tests.usage.test_writer import sample_record

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def linked_receipt(repository: PostgresUsageRepository, cost: Decimal) -> UsageRecord:
    async with repository.sessions.begin() as session:
        org = Organization(name=f"reconcile-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        team = Team(organization_id=org.id, name="team")
        session.add(team)
        await session.flush()
        return replace(
            sample_record(),
            organization_id=org.id,
            team_id=team.id,
            created_at=datetime.now(UTC),
            cost_status="priced",
            cost_usd=cost,
        )


async def test_budget_increment_lost_during_outage_heals_from_postgres(
    migrated_database: str,
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    record = await linked_receipt(repository, Decimal("0.000002025000"))
    team = record.team_id
    await repository.insert(
        [
            replace(
                record,
                id=uuid.uuid4(),
                request_id="before-outage",
                cost_usd=Decimal("0.000006750000"),
            )
        ]
    )
    key = f"lgw:budget:{team}:{record.created_at:%Y-%m}"
    await test_redis.set(key, picos(Decimal("0.000006750000")), ex=3600)
    service = LimitService(test_redis, fail_mode="open")
    limits = EffectiveLimits(0, 0, 0, Decimal("1"), Decimal("0.8"))
    writer = UsageWriter(repository.insert, batch_size=1, interval=0.01)
    original_call = service.scripts.call

    async def outage(name: str, keys: list[str], args: list[str | int | float]) -> list[int] | int:
        if name == "budget" and int(args[1]) > 0:
            raise ConnectionError("simulated lost increment")
        return await original_call(name, keys, args)

    monkeypatch.setattr(service.scripts, "call", outage)
    try:
        writer.start()
        for index in range(3):
            priced = replace(record, id=uuid.uuid4(), request_id=f"outage-{index}")
            await service.finish(team, None, priced, limits)
            writer.enqueue(priced)
        await writer.stop()
        monkeypatch.setattr(service.scripts, "call", original_call)

        reconciler = BudgetReconciler(service, repository, writer)
        await reconciler.run_once()
        durable = await repository.month_spend(
            team,
            record.created_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            month_end(record.created_at),
        )
        stored = await test_redis.get(key)

        assert stored is not None
        assert int(stored) == picos(durable)
        assert durable == Decimal("0.000012825000")
    finally:
        await engine.dispose()


async def test_pending_writer_receipt_is_included_without_double_counting(
    migrated_database: str,
    test_redis: Redis,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    receipt = await linked_receipt(repository, Decimal("0.125000000001"))
    team = receipt.team_id
    key = f"lgw:budget:{team}:{receipt.created_at:%Y-%m}"
    await test_redis.set(key, 0, ex=3600)
    writer = UsageWriter(repository.insert, batch_size=1, interval=0.01)
    writer.enqueue(receipt)
    reconciler = BudgetReconciler(LimitService(test_redis), repository, writer)
    try:
        await reconciler.run_once()
        pending_value = await test_redis.get(key)
        writer.start()
        await writer.stop()
        await reconciler.run_once()
        durable_value = await test_redis.get(key)

        assert pending_value is not None
        assert int(pending_value) == picos(Decimal("0.125000000001"))
        assert durable_value == pending_value
    finally:
        await engine.dispose()


async def test_reconciliation_does_not_erase_spend_from_another_replica(
    migrated_database: str,
    test_redis: Redis,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    receipt = await linked_receipt(repository, Decimal("0.5"))
    await repository.insert([receipt])
    key = f"lgw:budget:{receipt.team_id}:{receipt.created_at:%Y-%m}"
    await test_redis.set(key, picos(Decimal("0.6")), ex=3600)
    reconciler = BudgetReconciler(
        LimitService(test_redis), repository, UsageWriter(repository.insert)
    )
    try:
        await reconciler.run_once()

        stored = await test_redis.get(key)
        assert stored is not None
        assert int(stored) == picos(Decimal("0.6"))
    finally:
        await engine.dispose()


async def test_reconciler_does_not_steal_another_replicas_lock(
    migrated_database: str,
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    receipt = await linked_receipt(repository, Decimal("0.75"))
    await repository.insert([receipt])
    key = f"lgw:budget:{receipt.team_id}:{receipt.created_at:%Y-%m}"
    await test_redis.set(key, 0, ex=3600)
    await test_redis.set(f"{key}:lock", "other-replica", ex=5)
    reconciler = BudgetReconciler(
        LimitService(test_redis), repository, UsageWriter(repository.insert)
    )
    reads = 0
    original = repository.month_spend

    async def counted_spend(team: uuid.UUID, start: datetime, end: datetime) -> Decimal:
        nonlocal reads
        if team == receipt.team_id:
            reads += 1
        return await original(team, start, end)

    monkeypatch.setattr(repository, "month_spend", counted_spend)
    try:
        await reconciler.run_once()
        assert await test_redis.get(key) == b"0"
        assert await test_redis.get(f"{key}:lock") == b"other-replica"
        assert reads == 0
        await test_redis.delete(f"{key}:lock")
        await reconciler.run_once()
        assert int(await test_redis.get(key)) == picos(Decimal("0.75"))
        assert reads == 1
    finally:
        await engine.dispose()


async def test_lifespan_worker_reconciles_without_an_http_request(
    migrated_database: str,
    test_redis: Redis,
    settings: Settings,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    receipt = await linked_receipt(repository, Decimal("0.125"))
    await repository.insert([receipt])
    key = f"lgw:budget:{receipt.team_id}:{receipt.created_at:%Y-%m}"
    await test_redis.set(key, 0, ex=3600)

    class Store(DatabaseTestStore):
        def get(self, name: str) -> SecretStr | None:
            if name == "redis_url":
                return SecretStr(os.environ["GATEWAY_TEST_REDIS_URL"])
            return super().get(name)

    configured = settings.model_copy(
        update={"limits": settings.limits.model_copy(update={"budget_reconcile_interval_s": 0.02})}
    )
    app = create_app(configured, secret_store=Store(migrated_database))
    try:
        async with app.router.lifespan_context(app):
            async with asyncio.timeout(2):
                for _ in range(200):
                    if await test_redis.get(key) == str(picos(Decimal("0.125"))).encode():
                        break
                    await asyncio.sleep(0.01)
                else:
                    pytest.fail("Background reconciliation did not update Redis")
    finally:
        await engine.dispose()
