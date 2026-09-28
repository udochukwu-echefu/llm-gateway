from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.tenants.repository import PostgresKeyRepository


@pytest.fixture
async def repository(migrated_database: str) -> AsyncIterator[PostgresKeyRepository]:
    engine = create_async_engine(migrated_database)
    try:
        yield PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()
