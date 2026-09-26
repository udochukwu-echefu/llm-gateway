import os
import uuid
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
from pydantic import SecretStr

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.main import create_app
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import KeyRecord
from tests.conftest import MemoryKeyRepository
from tests.live.models import PROVIDERS, LiveProvider, resolve_live_models


@pytest.fixture(params=PROVIDERS, ids=lambda provider: provider.name)
def live_provider(request: pytest.FixtureRequest) -> LiveProvider:
    provider = cast(LiveProvider, request.param)
    if not os.environ.get(f"GATEWAY_PROVIDERS__{provider.name.upper()}__API_KEY"):
        pytest.skip(f"No environment key configured for {provider.name}")
    return resolve_live_models(provider)


@pytest.fixture
async def live_client(live_provider: LiveProvider) -> AsyncIterator[httpx.AsyncClient]:
    prefix = f"GATEWAY_PROVIDERS__{live_provider.name.upper()}__"
    block = {"api_key": os.environ[prefix + "API_KEY"]}
    if prefix + "BASE_URL" in os.environ:
        block["base_url"] = os.environ[prefix + "BASE_URL"]
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # live tests use environment only
        providers=ProvidersSettings.model_validate({live_provider.name: block}),
    )
    pepper = b"fake-live-test-pepper-32-bytes-minimum"
    issued = issue_key(pepper)
    repo = MemoryKeyRepository()
    repo.records[issued.key_id] = KeyRecord(
        issued.key_id, issued.secret_hash, uuid.uuid4(), uuid.uuid4()
    )

    class LiveStore:
        def get(self, name: str) -> SecretStr | None:
            if name == "api_key_pepper":
                return SecretStr(pepper.decode())
            if name == "database_url":
                return SecretStr("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
            if name == f"providers__{live_provider.name}__api_key":
                return SecretStr(block["api_key"])
            return None

    app = create_app(settings, key_repository=repo, secret_store=LiveStore())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued.full_key}"},
        ) as client,
    ):
        yield client
