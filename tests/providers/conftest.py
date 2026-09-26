from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.providers.registry import ADAPTER_TYPES
from llm_gateway.schemas.common import ProviderName
from tests.conftest import UPSTREAM_KEY, UPSTREAM_URL


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
