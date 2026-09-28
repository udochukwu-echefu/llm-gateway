import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.tenants.models import AdminKey
from tests.tenants.support import run_admin

pytestmark = pytest.mark.db


async def test_cli_bootstraps_admin_key_without_storing_secret(migrated_database: str) -> None:
    full_key = run_admin(
        migrated_database, "create-admin-key", "fake-bootstrap", "--role", "platform"
    )
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(
                select(AdminKey).where(AdminKey.key_id == full_key.split("_")[1])
            )
    finally:
        await engine.dispose()

    assert full_key.startswith("lgwa_")
    assert row is not None
    assert row.role == "platform"
    assert full_key.encode() not in row.secret_hash
