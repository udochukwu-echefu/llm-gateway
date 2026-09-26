import os
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.models import ApiKey
from llm_gateway.tenants.repository import PostgresKeyRepository
from tests.conftest import TEST_PEPPER

pytestmark = pytest.mark.db


async def test_migration_upgrades_empty_database(migrated_database: str) -> None:
    engine = create_async_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            tables = (
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                )
                .scalars()
                .all()
            )

        assert {"organizations", "teams", "api_keys", "alembic_version"} <= set(tables)
    finally:
        await engine.dispose()


async def test_repository_key_contract_and_no_plaintext_in_database(migrated_database: str) -> None:
    from llm_gateway.tenants.keys import issue_key

    engine = create_async_engine(migrated_database)
    repo = PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False))
    org = f"org-{os.urandom(4).hex()}"
    issued = issue_key(TEST_PEPPER.encode())
    try:
        await repo.create_org(org)
        await repo.create_team(org, "team")
        await repo.create_key(org, "team", "example", issued.key_id, issued.secret_hash)
        record = await repo.get_key(issued.key_id)
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(select(ApiKey).where(ApiKey.key_id == issued.key_id))

        assert record is not None
        assert row is not None
        assert row.secret_hash == issued.secret_hash
        assert issued.full_key.split("_", 2)[2].encode() not in row.secret_hash
        assert issued.full_key.split("_", 2)[2].encode() not in str(row.__dict__).encode()
        assert record.organization_id is not None
        assert await repo.revoke_key(issued.key_id)
        revoked = await repo.get_key(issued.key_id)
        assert revoked is not None
        assert revoked.revoked_at is not None
        assert len(await repo.list_keys(org, "team")) == 1
    finally:
        await engine.dispose()


async def test_cli_create_use_revoke_and_expiry(migrated_database: str, settings: Settings) -> None:
    env = {
        **os.environ,
        "GATEWAY_DATABASE_URL": migrated_database,
        "GATEWAY_API_KEY_PEPPER": TEST_PEPPER,
    }
    org = f"cli-{os.urandom(4).hex()}"

    # Exercise the console entry point's main function through the installed script.
    def admin(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603  # fixed executable, no shell
            [str(Path(__file__).resolve().parents[2] / ".venv/bin/gateway-admin"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    assert "Created organization" in admin("create-org", org)
    assert "Created team" in admin("create-team", org, "team")
    full_key = admin("create-key", org, "team", "client", "--expires-in-days", "1")
    assert full_key.startswith("lgw_")
    assert "\n" not in full_key
    key_id = full_key.split("_")[1]
    listing = admin("list-keys", org)
    assert key_id in listing
    assert "active" in listing
    assert full_key not in listing
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine)() as session:
            stored = await session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))
        assert stored is not None
        assert full_key.split("_", 2)[2].encode() not in stored.secret_hash
    finally:
        await engine.dispose()

    clock = [0.0]
    configured = settings.model_copy(
        update={
            "database_url": SecretStr(migrated_database),
            "api_key_pepper": SecretStr(TEST_PEPPER),
        }
    )

    # The environment-based store uses fixture values, so inject explicit store values here.
    class Store:
        def get(self, name: str) -> SecretStr | None:
            if name == "database_url":
                return SecretStr(migrated_database)
            if name == "api_key_pepper":
                return SecretStr(TEST_PEPPER)
            if name == "providers__groq__api_key" or name == "providers__openai__api_key":
                return SecretStr("fake-provider-key")
            return None

    app: FastAPI = create_app(
        configured, secret_store=Store(), key_cache=VerifiedKeyCache(ttl=30, clock=lambda: clock[0])
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        first = await client.post(
            "/v1/chat/completions", json={}, headers={"authorization": f"Bearer {full_key}"}
        )
        assert "Key revoked" in admin("revoke-key", key_id)
        still_valid = await client.post(
            "/v1/chat/completions", json={}, headers={"authorization": f"Bearer {full_key}"}
        )
        clock[0] = 30
        rejected = await client.post(
            "/v1/chat/completions", json={}, headers={"authorization": f"Bearer {full_key}"}
        )
        ready = await client.get("/readyz")

    assert first.status_code == still_valid.status_code == 400
    assert rejected.status_code == 401
    assert ready.status_code == 200
