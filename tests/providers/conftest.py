import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import cast

import httpx
import pytest

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.main import create_app
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.providers.registry import ADAPTER_TYPES
from llm_gateway.schemas.common import ProviderName
from llm_gateway.usage.record import UsageRecord
from tests.conftest import UPSTREAM_KEY, UPSTREAM_URL, MemoryKeyRepository, OfflineLimitService


@pytest.fixture(params=tuple(ADAPTER_TYPES))
def provider_name(request: pytest.FixtureRequest) -> ProviderName:
    return cast(ProviderName, request.param)


@pytest.fixture
def settings(provider_name: ProviderName) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # pydantic-settings runtime option
        providers=ProvidersSettings.model_validate(
            {
                provider_name: {"api_key": UPSTREAM_KEY, "base_url": UPSTREAM_URL},
            }
        ),
        log_format="console",
    )


@pytest.fixture
async def adapter(provider_name: ProviderName) -> AsyncIterator[OpenAICompatibleAdapter]:
    async with httpx.AsyncClient(base_url=UPSTREAM_URL) as http:
        yield ADAPTER_TYPES[provider_name](http)


@dataclass
class HostedGateway:
    client: httpx.AsyncClient
    records: list[UsageRecord]
    recorded: asyncio.Event


@pytest.fixture
async def hosted_gateway(
    settings: Settings, memory_repository: MemoryKeyRepository, issued_test_key: str
) -> AsyncIterator[HostedGateway]:
    records: list[UsageRecord] = []
    recorded = asyncio.Event()

    async def sink(batch: Sequence[UsageRecord]) -> None:
        records.extend(batch)
        recorded.set()

    settings.usage_batch_size = 1
    settings.resilience.max_retries = 0
    app = create_app(
        settings,
        key_repository=memory_repository,
        usage_sink=sink,
        limit_service=OfflineLimitService(),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        yield HostedGateway(client, records, recorded)
