import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.config import Settings
from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.models import ApiKey
from tests.tenants.support import create_cli_key, database_app, run_admin, unique_name

pytestmark = pytest.mark.db


async def test_cli_creates_organization_and_team(migrated_database: str) -> None:
    org = unique_name("cli")

    created_org = run_admin(migrated_database, "create-org", org)
    created_team = run_admin(migrated_database, "create-team", org, "team")

    assert "Created organization" in created_org
    assert org in created_org
    assert "Created team team" in created_team


async def test_cli_create_key_prints_only_full_key_once(migrated_database: str) -> None:
    issued = create_cli_key(migrated_database)

    assert issued.full_key.startswith("lgw_")
    assert "\n" not in issued.full_key


async def test_cli_list_keys_never_shows_secret(migrated_database: str) -> None:
    issued = create_cli_key(migrated_database)

    listing = run_admin(migrated_database, "list-keys", issued.org, issued.team)

    assert issued.key_id in listing
    assert "client" in listing
    assert "active" in listing
    assert issued.full_key not in listing


async def test_cli_sets_shows_and_clears_team_limits(migrated_database: str) -> None:
    issued = create_cli_key(migrated_database)

    changed = run_admin(
        migrated_database,
        "set-limits",
        issued.org,
        issued.team,
        "--rpm",
        "5",
        "--tpm",
        "10",
        "--max-concurrency",
        "2",
    )
    budget = run_admin(
        migrated_database,
        "set-budget",
        issued.org,
        issued.team,
        "1.250000000001",
        "--alert-at",
        "0.9",
    )
    cleared = run_admin(migrated_database, "clear-limits", issued.org, issued.team)

    assert "rpm=5" in changed
    assert "tpm=10" in changed
    assert "monthly_budget_usd=Decimal('1.250000000001')" in budget
    assert "rpm=None" in cleared
    assert "monthly_budget_usd=None" in cleared


@pytest.mark.redis
async def test_cli_shows_live_redis_usage(
    migrated_database: str,
    test_redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = create_cli_key(migrated_database)
    monkeypatch.setenv("GATEWAY_REDIS_URL", os.environ["GATEWAY_TEST_REDIS_URL"])
    run_admin(migrated_database, "set-limits", issued.org, issued.team, "--rpm", "5")

    shown = run_admin(migrated_database, "show-limits", issued.org, issued.team)

    assert "requests_remaining=5" in shown
    assert "active_leases=0" in shown


async def test_cli_key_authenticates_through_postgres(
    migrated_database: str, settings: Settings
) -> None:
    issued = create_cli_key(migrated_database)
    app = database_app(settings, migrated_database)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.post(
            "/v1/chat/completions", json={}, headers={"authorization": f"Bearer {issued.full_key}"}
        )

    assert response.status_code == 400  # authenticated; invalid body rejected


async def test_cli_revoke_key_is_rejected_after_original_cache_ttl(
    migrated_database: str, settings: Settings
) -> None:
    issued = create_cli_key(migrated_database)
    clock = [0.0]
    app: FastAPI = database_app(
        settings, migrated_database, VerifiedKeyCache(ttl=30, clock=lambda: clock[0])
    )
    headers = {"authorization": f"Bearer {issued.full_key}"}

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        first = await client.post("/v1/chat/completions", json={}, headers=headers)
        revoked = run_admin(migrated_database, "revoke-key", issued.key_id)
        clock[0] = 20
        cached = await client.post("/v1/chat/completions", json={}, headers=headers)
        clock[0] = 35
        rejected = await client.post("/v1/chat/completions", json={}, headers=headers)

    assert first.status_code == 400
    assert revoked == "Key revoked"
    assert cached.status_code == 400
    assert rejected.status_code == 401


async def test_cli_expiry_is_stored_as_utc_datetime(migrated_database: str) -> None:
    issued = create_cli_key(migrated_database, expires_in_days=1)
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(select(ApiKey).where(ApiKey.key_id == issued.key_id))

        assert row is not None
        assert row.expires_at is not None
        assert row.expires_at.tzinfo is not None
        assert row.expires_at > datetime.now(UTC)
    finally:
        await engine.dispose()


async def test_cli_expired_key_is_rejected_by_app(
    migrated_database: str, settings: Settings
) -> None:
    issued = create_cli_key(migrated_database, expires_in_days=1)
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine).begin() as session:
            row = await session.scalar(select(ApiKey).where(ApiKey.key_id == issued.key_id))
            assert row is not None
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    finally:
        await engine.dispose()
    app = database_app(settings, migrated_database)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.post(
            "/v1/chat/completions", json={}, headers={"authorization": f"Bearer {issued.full_key}"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
