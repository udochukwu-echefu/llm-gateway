import asyncio
import base64
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from llm_gateway.catalog import Catalog, load_catalog
from llm_gateway.config import Settings
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import KeyRecord
from llm_gateway.usage.record import UsageRecord

UPSTREAM_URL = "https://upstream.test/v1"
UPSTREAM_KEY = "sk-upstream-test"
TEST_PEPPER = "fake-pepper-for-tests-only-32-bytes-minimum"
TEST_DATABASE_URL = "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake"


class MemoryKeyRepository:
    def __init__(self) -> None:
        self.records: dict[str, KeyRecord] = {}
        self.available = True

    async def get_key(self, key_id: str) -> KeyRecord | None:
        return self.records.get(key_id)

    async def ping(self) -> None:
        if not self.available:
            raise ConnectionError("database unavailable")


class OfflineRedis(Redis):
    async def ping(self, **kwargs: object) -> bool:
        return True


class OfflineLimitService(LimitService):
    """No network I/O in ordinary tests; real limit behavior uses the redis marker."""

    def __init__(self) -> None:
        super().__init__(OfflineRedis())

    async def ip_check(self, ip: str) -> None:
        pass

    async def ip_failure(self, ip: str) -> None:
        pass

    async def admission(
        self, team: uuid.UUID, limits: EffectiveLimits
    ) -> tuple[str | None, dict[str, str]]:
        return None, {}

    async def request_admission(self, team: uuid.UUID, limits: EffectiveLimits) -> dict[str, str]:
        return {}

    async def remaining_admission(
        self, team: uuid.UUID, limits: EffectiveLimits, rpm_headers: dict[str, str]
    ) -> tuple[str | None, dict[str, str]]:
        return None, rpm_headers

    async def finish(
        self,
        team: uuid.UUID,
        lease: str | None,
        record: UsageRecord | None,
        limits: EffectiveLimits,
    ) -> None:
        pass


@pytest.fixture(autouse=True)
def offline_by_default(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Ordinary tests cannot use developer credentials or accidentally reach the network."""
    if "live" in request.keywords:
        yield
        return
    for name in os.environ:
        if name.startswith("GATEWAY_PROVIDERS") or name in {
            "GATEWAY_DATABASE_URL",
            "GATEWAY_API_KEY_PEPPER",
            "GATEWAY_SECRETS__BACKEND",
        }:
            monkeypatch.delenv(name)
    monkeypatch.setenv("GATEWAY_METRICS__ENABLED", "false")
    monkeypatch.delenv("GATEWAY_TRACING__OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("GATEWAY_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("GATEWAY_API_KEY_PEPPER", TEST_PEPPER)
    monkeypatch.setenv("GATEWAY_CACHE_ENCRYPTION_KEY", base64.b64encode(b"a" * 32).decode())
    monkeypatch.setenv("GATEWAY_CACHE__ENABLED", "false")
    with respx.mock(assert_all_called=False):
        yield


@pytest.fixture
async def test_redis() -> AsyncIterator[Redis]:
    url = os.getenv("GATEWAY_TEST_REDIS_URL")
    if not url:
        if os.getenv("CI", "").lower() == "true":
            pytest.fail("CI requires GATEWAY_TEST_REDIS_URL for Redis tests")
        pytest.skip("GATEWAY_TEST_REDIS_URL unset; Redis tests skipped locally")
    client = Redis.from_url(url)  # pyright: ignore[reportUnknownMemberType]  # redis-py types **kwargs as Unknown
    try:
        await client.ping()  # pyright: ignore[reportUnknownMemberType]  # redis-py types **kwargs as Unknown
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # never read a developer's real .env
        providers={
            "groq": {"base_url": UPSTREAM_URL, "api_key": UPSTREAM_KEY},
            "openai": {"base_url": UPSTREAM_URL, "api_key": UPSTREAM_KEY},
        },
        log_format="console",
        max_request_bytes=4096,
        cache={"enabled": False},
    )


@pytest.fixture
def issued_test_key() -> str:
    return issue_key(TEST_PEPPER.encode()).full_key


@pytest.fixture
def memory_repository(issued_test_key: str) -> MemoryKeyRepository:
    repository = MemoryKeyRepository()
    _, key_id, secret = issued_test_key.split("_", 2)
    from llm_gateway.tenants.keys import hash_secret

    repository.records[key_id] = KeyRecord(
        key_id, hash_secret(TEST_PEPPER.encode(), secret), uuid.uuid4(), uuid.uuid4()
    )
    return repository


@pytest.fixture
def test_catalog() -> Catalog:
    base = load_catalog()
    entries = list(base.models)
    for provider, model, kind in (
        ("groq", "llama-3.3-70b-versatile", "chat"),
        ("groq", "nope", "chat"),
        ("openai", "text-embedding-004", "embedding"),
        *((name, "vendor/model", "chat") for name in ("groq", "deepseek", "gemini", "openai")),
        *((name, "model", "chat") for name in ("groq", "deepseek", "gemini", "openai")),
        *((name, "nested/model", "chat") for name in ("groq", "deepseek", "gemini", "openai")),
        *((name, "embedding", "embedding") for name in ("gemini", "openai")),
        ("gemini", "gemini-embedding-001", "embedding"),
    ):
        template = next(entry for entry in base.models if entry.kind == kind)
        entries.append(template.model_copy(update={"provider": provider, "model": model}))
    return Catalog.model_validate({"version": "test-only", "models": entries})


@pytest.fixture
def app(
    settings: Settings, memory_repository: MemoryKeyRepository, test_catalog: Catalog
) -> FastAPI:
    return create_app(
        settings,
        key_repository=memory_repository,
        catalog=test_catalog,
        limit_service=OfflineLimitService(),
    )


@pytest.fixture
async def client(app: FastAPI, issued_test_key: str) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as c:
            yield c


@pytest.fixture
def upstream() -> Iterator[respx.MockRouter]:
    # Any request to an unmocked URL fails the test, so nothing can reach a real provider.
    with respx.mock(base_url=UPSTREAM_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """Migrate an isolated database; never reuse development or CI's main schema."""
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
