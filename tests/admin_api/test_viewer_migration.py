"""Exercise real upgrade/downgrade on an additional disposable database."""

import asyncio
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from tests.conftest import TEST_PEPPER

pytestmark = pytest.mark.db


async def test_viewer_migration_upgrade_and_refusing_downgrade(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "viewer_migration_" + uuid.uuid4().hex
    base = make_url(migrated_database)
    owner = create_async_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    url = base.set(database=name).render_as_string(hide_password=False)
    async with owner.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(url)
    monkeypatch.setenv("GATEWAY_DATABASE_URL", url)
    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "0011")
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        admin = AdminService(sessions, TEST_PEPPER.encode(), "migration-test")
        org = await admin.create_org("fake-migration")
        for scope in (None, org.name):
            await admin.create_admin_key("fake-migration-viewer", "viewer", scope)
        with pytest.raises(RuntimeError, match="Cannot downgrade 0012 while viewer keys exist"):
            await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0011")
        async with sessions.begin() as session:
            await session.execute(
                text("UPDATE admin_keys SET revoked_at=now() WHERE role='viewer'")
            )
        with pytest.raises(RuntimeError, match="including revoked keys"):
            await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0011")
        async with sessions.begin() as session:
            await session.execute(text("DELETE FROM admin_keys WHERE role='viewer'"))
        await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0011")
        async with sessions() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0011"
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
    finally:
        await engine.dispose()
        async with owner.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await owner.dispose()
