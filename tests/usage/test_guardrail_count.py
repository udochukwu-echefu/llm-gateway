from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.catalog import load_catalog
from llm_gateway.tenants.auth import Principal
from llm_gateway.tenants.repository import PostgresKeyRepository
from llm_gateway.usage.record import UsageEvent
from llm_gateway.usage.repository import PostgresUsageRepository, UsageRow
from tests.tenants.support import unique_name

pytestmark = pytest.mark.db


async def test_redaction_count_round_trips_and_legacy_null_is_preserved(
    migrated_database: str,
) -> None:
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        tenants = PostgresKeyRepository(sessions)
        org = await tenants.create_org(unique_name("redaction"))
        team = await tenants.create_team(org.name, "team")
        catalog = load_catalog()
        event = UsageEvent(
            Principal(org.id, team.id, "fakekeyid"),
            "fake-request",
            catalog.models[0],
            catalog,
            "chat",
            False,
        )
        old = event.finish(1, 1)
        new = replace(event.finish(1, 1), redaction_count=3)

        await PostgresUsageRepository(sessions).insert([old, new])

        async with sessions() as session:
            legacy = await session.get(UsageRow, old.id)
            current = await session.get(UsageRow, new.id)
        assert legacy is not None
        assert legacy.redaction_count is None
        assert current is not None
        assert current.redaction_count == 3
    finally:
        await engine.dispose()
