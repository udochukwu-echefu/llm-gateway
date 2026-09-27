import os
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from typing import cast

import httpx
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.service import ResponseCache
from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.gateway_state import get_app_state
from llm_gateway.main import create_app
from llm_gateway.secrets import EnvSecretStore
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import KeyRecord
from llm_gateway.usage.record import UsageRecord
from tests.conftest import MemoryKeyRepository, OfflineLimitService
from tests.live.models import PROVIDERS, LiveProvider, resolve_live_models


@pytest.fixture(params=PROVIDERS, ids=lambda provider: provider.name)
def live_provider(request: pytest.FixtureRequest) -> LiveProvider:
    provider = cast(LiveProvider, request.param)
    if not os.environ.get(f"GATEWAY_PROVIDERS__{provider.name.upper()}__API_KEY"):
        pytest.skip(f"No environment key configured for {provider.name}")
    return resolve_live_models(provider)


@pytest.fixture
def live_records() -> list[UsageRecord]:
    return []


@pytest.fixture
async def live_client(
    live_provider: LiveProvider, live_records: list[UsageRecord]
) -> AsyncIterator[httpx.AsyncClient]:
    prefix = f"GATEWAY_PROVIDERS__{live_provider.name.upper()}__"
    block = {"api_key": os.environ[prefix + "API_KEY"]}
    if prefix + "BASE_URL" in os.environ:
        block["base_url"] = os.environ[prefix + "BASE_URL"]
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # live tests use environment only
        providers=ProvidersSettings.model_validate({live_provider.name: block}),
        usage_batch_size=1,
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
            if name in {"cache_encryption_key", "redis_url"}:
                return EnvSecretStore().get(name)
            return None

    async def sink(records: Sequence[UsageRecord]) -> None:
        live_records.extend(records)

    app = create_app(
        settings,
        key_repository=repo,
        secret_store=LiveStore(),
        usage_sink=sink,
        limit_service=OfflineLimitService(),
    )
    redis_secret = LiveStore().get("redis_url")
    redis_client = (
        Redis.from_url(redis_secret.get_secret_value())  # pyright: ignore[reportUnknownMemberType]  # redis-py types **kwargs as Unknown
        if redis_secret is not None
        else None
    )
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gateway.test",
                headers={"authorization": f"Bearer {issued.full_key}"},
            ) as client,
        ):
            state = get_app_state(app)
            cache_key = LiveStore().get("cache_encryption_key")
            if redis_client is not None and cache_key is not None and state.response_cache:
                app.state.gateway = replace(
                    state,
                    response_cache=ResponseCache(
                        redis_client,
                        CacheCipher(cache_key),
                        timeout=settings.limits.redis_timeout_s,
                        metrics=state.telemetry.metrics if state.telemetry else None,
                    ),
                )
            yield client
    finally:
        if redis_client is not None:
            await redis_client.aclose()
