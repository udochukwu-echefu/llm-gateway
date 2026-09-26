"""Alembic uses the same database URL as the app, without printing credentials."""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from llm_gateway.tenants.models import Base

target_metadata = Base.metadata


async def run_migrations() -> None:
    url = os.environ.get("GATEWAY_DATABASE_URL")
    if not url:
        raise ValueError("GATEWAY_DATABASE_URL is required to run migrations")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(
                lambda sync_connection: context.configure(
                    connection=sync_connection, target_metadata=target_metadata
                )
            )
            async with connection.begin():
                await connection.run_sync(lambda _: context.run_migrations())
    finally:
        await engine.dispose()


asyncio.run(run_migrations())
