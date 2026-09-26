import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import cast

import httpx
import pytest

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.main import create_app
from llm_gateway.schemas.common import ProviderName


@dataclass(frozen=True)
class LiveProvider:
    name: ProviderName
    chat_model: str
    embedding_model: str | None


PROVIDERS = (
    LiveProvider("groq", "llama-3.1-8b-instant", None),
    LiveProvider("deepseek", "deepseek-flash", None),
    LiveProvider("gemini", "gemini-3.8-flash", "gemini-embedding-001"),
    LiveProvider("openai", "gpt-4.1-nano", "text-embedding-3-small"),
)


@pytest.fixture(params=PROVIDERS, ids=lambda provider: provider.name)
def live_provider(request: pytest.FixtureRequest) -> LiveProvider:
    provider = cast(LiveProvider, request.param)
    if not os.environ.get(f"GATEWAY_PROVIDERS__{provider.name.upper()}__API_KEY"):
        pytest.skip(f"No environment key configured for {provider.name}")
    return provider


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
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
        ) as client,
    ):
        yield client
