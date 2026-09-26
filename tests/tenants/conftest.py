import asyncio
import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    base_url = os.getenv("GATEWAY_TEST_DATABASE_URL")
    if not base_url:
        if os.getenv("CI", "").lower() == "true":
            pytest.fail("CI requires GATEWAY_TEST_DATABASE_URL for database tests")
        pytest.skip("GATEWAY_TEST_DATABASE_URL unset; Postgres tests skipped locally")
    name = f"gateway_test_{uuid.uuid4().hex}"
    url = make_url(base_url)
    admin_url = url.set(database="postgres").render_as_string(hide_password=False)
    test_url = url.set(database=name).render_as_string(hide_password=False)

    async def create_database() -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
        finally:
            await engine.dispose()

    async def drop_database() -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        finally:
            await engine.dispose()

    try:
        asyncio.run(create_database())
    except Exception as exc:
        pytest.fail(f"Postgres unavailable for db tests: {type(exc).__name__}")
    previous = os.environ.get("GATEWAY_DATABASE_URL")
    try:
        os.environ["GATEWAY_DATABASE_URL"] = test_url
        command.upgrade(Config("alembic.ini"), "head")
        yield test_url
    finally:
        if previous is None:
            os.environ.pop("GATEWAY_DATABASE_URL", None)
        else:
            os.environ["GATEWAY_DATABASE_URL"] = previous
        asyncio.run(drop_database())
