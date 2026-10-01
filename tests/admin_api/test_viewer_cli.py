import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.tenants.models import AdminKey
from tests.admin_api.conftest import AdminHarness
from tests.tenants.support import run_admin

pytestmark = pytest.mark.db


@pytest.mark.parametrize("scoped", [False, True])
async def test_cli_creates_viewer_key(
    admin_harness: AdminHarness, migrated_database: str, scoped: bool
) -> None:
    args = ("--org", admin_harness.org) if scoped else ()
    key = run_admin(
        migrated_database, "create-admin-key", "fake-viewer-cli", "--role", "viewer", *args
    )
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(select(AdminKey).where(AdminKey.key_id == key.split("_")[1]))
        assert row is not None
        assert row.role == "viewer"
        assert (row.organization_id is not None) == scoped
        assert key.encode() not in row.secret_hash
    finally:
        await engine.dispose()
