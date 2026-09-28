"""Alembic uses the same database URL as the app, without printing credentials."""

import asyncio
import os
from pathlib import Path

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from llm_gateway.audit.models import AuditEvent  # noqa: F401
from llm_gateway.secrets import FileSecretStore
from llm_gateway.tenants.models import Base

target_metadata = Base.metadata


async def run_migrations() -> None:
    backend = os.environ.get("GATEWAY_SECRETS__BACKEND", "env")
    if backend == "file":
        directory = os.environ.get("GATEWAY_SECRETS__DIR")
        if not directory:
            raise ValueError("GATEWAY_SECRETS__DIR is required to run migrations")
        secret = FileSecretStore(Path(directory)).get("database_url")
        url = secret.get_secret_value() if secret else None
    elif backend == "env":
        url = os.environ.get("GATEWAY_DATABASE_URL")
    else:
        raise ValueError("GATEWAY_SECRETS__BACKEND must be env or file")
    if not url:
        raise ValueError("GATEWAY_DATABASE_URL is required to run migrations")
    engine = create_async_engine(url, hide_parameters=True)
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
