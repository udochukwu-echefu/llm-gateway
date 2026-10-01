import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_gateway.admin.api.app import create_admin_app
from llm_gateway.admin.api.auth import AdminContext
from llm_gateway.admin.service.service import AdminService
from llm_gateway.config import CacheSettings, ProviderSettings, ProvidersSettings, Settings
from tests.conftest import TEST_PEPPER


class EmptyCache:
    async def scan_iter(self, **kwargs: object) -> AsyncIterator[bytes]:
        if False:
            yield b""

    async def unlink(self, *keys: bytes) -> int:
        return 0


@dataclass
class AdminHarness:
    app: FastAPI
    client: httpx.AsyncClient
    org: str
    other: str
    platform_key: str
    org_key: str
    team_key: str
    other_team_key: str
    sessions: async_sessionmaker[AsyncSession]

    def headers(self, key: str) -> dict[str, str]:
        return {"authorization": f"Bearer {key}"}


@pytest.fixture
async def admin_harness(migrated_database: str) -> AsyncIterator[AdminHarness]:
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    bootstrap = AdminService(sessions, TEST_PEPPER.encode(), "cli-test")
    org = f"admin-{uuid.uuid4().hex}"
    other = f"other-{uuid.uuid4().hex}"
    await bootstrap.create_org(org)
    await bootstrap.create_org(other)
    await bootstrap.create_team(org, "team")
    await bootstrap.create_team(other, "team")
    team_key = await bootstrap.create_key(org, "team", "fake-client")
    other_team_key = await bootstrap.create_key(other, "team", "fake-client")
    platform_key = await bootstrap.create_admin_key("fake-platform", "platform", None)
    org_key = await bootstrap.create_admin_key("fake-org", "org", org)
    app = create_admin_app(
        AdminContext(
            sessions,
            TEST_PEPPER.encode(),
            None,
            cast(Redis, EmptyCache()),
            # Construct fake settings without reading a developer's .env.
            settings=Settings.model_construct(
                providers=ProvidersSettings(
                    groq=ProviderSettings(api_key=SecretStr("obviously-fake-platform-fixture"))
                ),
                cache=CacheSettings(enabled=False),
            ),
        )
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://admin.test"
        ) as client:
            yield AdminHarness(
                app, client, org, other, platform_key, org_key, team_key, other_team_key, sessions
            )
    finally:
        await engine.dispose()
