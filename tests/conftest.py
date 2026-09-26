import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import respx
from fastapi import FastAPI

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import KeyRecord

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
    monkeypatch.setenv("GATEWAY_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("GATEWAY_API_KEY_PEPPER", TEST_PEPPER)
    with respx.mock(assert_all_called=False):
        yield


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
def app(settings: Settings, memory_repository: MemoryKeyRepository) -> FastAPI:
    return create_app(settings, key_repository=memory_repository)


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
