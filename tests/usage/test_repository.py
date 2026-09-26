import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.usage.repository import PostgresUsageRepository, UsageRow
from tests.tenants.support import run_admin
from tests.usage.test_writer import sample_record

pytestmark = pytest.mark.db


async def test_insert_round_trips_numeric_exactly_and_preserves_original_price(
    migrated_database: str,
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    record = await _linked_record(migrated_database)
    priced = replace(record, cost_usd=Decimal("0.000000000123"))
    try:
        await repository.insert([priced])
        async with repository.sessions() as session:
            stored = await session.scalar(select(UsageRow).where(UsageRow.id == priced.id))
        assert stored is not None
        assert stored.cost_usd == Decimal("0.000000000123")
        assert stored.catalog_version == priced.catalog_version
        assert stored.organization_id == priced.organization_id
        assert stored.created_at.tzinfo is not None
        assert stored.stream is False

        changed_price = replace(
            priced, id=uuid.uuid4(), catalog_version="next-version", cost_usd=Decimal("0.5")
        )
        await repository.insert([changed_price])
        async with repository.sessions() as session:
            original = await session.scalar(
                select(UsageRow.cost_usd).where(UsageRow.id == priced.id)
            )
        assert original == Decimal("0.000000000123")
    finally:
        await engine.dispose()


async def test_usage_cli_reports_aggregated_cost_and_missing_counts(
    migrated_database: str,
) -> None:
    from llm_gateway.tenants.models import Organization

    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    record = await _linked_record(migrated_database)
    try:
        await repository.insert(
            [
                record,
                replace(record, id=uuid.uuid4(), cost_status="stream_incomplete", cost_usd=None),
            ]
        )
        async with repository.sessions() as session:
            org = await session.scalar(
                select(Organization.name).where(Organization.id == record.organization_id)
            )
        assert org is not None

        report = run_admin(
            migrated_database,
            "usage",
            org,
            "--team",
            "team",
            "--group-by",
            "model",
            "--since",
            date.today().isoformat(),
            "--until",
            date.today().isoformat(),
        )

        assert "requests=2" in report
        assert "stream_incomplete=1" in report
        assert "cost_usd=1.234E-9" in report or "cost_usd=0.000000001234" in report
    finally:
        await engine.dispose()


@pytest.mark.parametrize("group_by", ["team", "key", "model", "day"])
async def test_sql_report_aggregates_by_each_group_and_counts_missing_costs(
    migrated_database: str,
    group_by: Literal["team", "key", "model", "day"],
) -> None:
    engine = create_async_engine(migrated_database)
    repository = PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
    record = await _linked_record(migrated_database)
    second = replace(
        record,
        id=uuid.uuid4(),
        request_id="next",
        cost_usd=None,
        cost_status="usage_missing",
        prompt_tokens=None,
    )
    try:
        await repository.insert([record, second])
        report = await repository.report(
            record.organization_id.hex, None, date.today(), date.today(), group_by
        )
        # report uses organization names, not UUIDs
        assert report == []
        from sqlalchemy import select

        from llm_gateway.tenants.models import Organization

        async with repository.sessions() as session:
            org = await session.scalar(
                select(Organization.name).where(Organization.id == record.organization_id)
            )
        assert org is not None
        report = await repository.report(org, None, date.today(), date.today(), group_by)

        assert len(report) == 1
        assert report[0]["requests"] == 2
        assert report[0]["usage_missing"] == 1
        assert report[0]["cost_usd"] == record.cost_usd
        assert report[0]["prompt_tokens"] == record.prompt_tokens
        assert await repository.report(org, "not-this-team", None, None, group_by) == []
        assert (
            await repository.report(org, None, date.today() + timedelta(days=1), None, group_by)
            == []
        )
    finally:
        await engine.dispose()


async def _linked_record(database_url: str):
    from llm_gateway.tenants.repository import PostgresKeyRepository

    engine = create_async_engine(database_url)
    try:
        keys = PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False))
        name = f"usage-{uuid.uuid4().hex}"
        key_id = uuid.uuid4().hex[:12]
        org = await keys.create_org(name)
        team = await keys.create_team(name, "team")
        await keys.create_key(name, "team", "key", key_id, b"x" * 32, None)
        return replace(
            sample_record(),
            organization_id=org.id,
            team_id=team.id,
            key_id=key_id,
            cost_usd=Decimal("0.000000001234"),
            cost_status="priced",
            prompt_tokens=2,
            completion_tokens=3,
            created_at=datetime.now(UTC),
        )
    finally:
        await engine.dispose()
