import httpx
import pytest

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.providers.defaults import DEFAULT_BASE_URLS
from llm_gateway.providers.pools import provider_pools


async def test_only_enabled_providers_have_separate_pools_closed_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[httpx.AsyncClient] = []
    original = httpx.AsyncClient

    class TrackingClient(original):
        async def __aenter__(self) -> httpx.AsyncClient:
            clients.append(self)
            return await super().__aenter__()

    monkeypatch.setattr(httpx, "AsyncClient", TrackingClient)
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # pydantic-settings runtime option
        providers=ProvidersSettings.model_validate(
            {
                "groq": {"api_key": "groq-test"},
                "openai": {"api_key": "openai-test"},
            }
        ),
    )

    async with provider_pools(settings) as registry:
        assert set(registry.adapters) == {"groq", "openai"}
        assert len(clients) == 2
        assert clients[0] is not clients[1]
        assert all(not client.is_closed for client in clients)
        assert clients[0].headers["authorization"] == "Bearer groq-test"
        assert clients[1].headers["authorization"] == "Bearer openai-test"
        assert str(clients[0].base_url).rstrip("/") == DEFAULT_BASE_URLS["groq"]
        assert str(clients[1].base_url).rstrip("/") == DEFAULT_BASE_URLS["openai"]

    assert all(client.is_closed for client in clients)
