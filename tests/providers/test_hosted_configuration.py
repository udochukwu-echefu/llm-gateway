from datetime import UTC, datetime
from typing import get_args

import httpx
import pytest
import respx

from llm_gateway.catalog import load_catalog
from llm_gateway.config import Settings
from llm_gateway.providers.pools import provider_pools
from llm_gateway.providers.registry import ADAPTER_TYPES
from llm_gateway.resilience.service import ResilienceService
from llm_gateway.routing.selection import available_models
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.providers.fixtures import hosted_completion


@pytest.mark.parametrize("name", ["zai", "nvidia"])
async def test_environment_key_enables_default_endpoint_and_missing_keys_stay_disabled(
    monkeypatch: pytest.MonkeyPatch, name: ProviderName, respx_mock: respx.MockRouter
) -> None:
    monkeypatch.setenv(f"GATEWAY_PROVIDERS__{name.upper()}__API_KEY", "fake-test-key")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # disable developer .env
    model = "glm-5.3-flash" if name == "zai" else "moonshotai/kimi-k3"
    url = (
        "https://api.z.ai/api/paas/v4/chat/completions"
        if name == "zai"
        else "https://integrate.api.nvidia.com/v1/chat/completions"
    )
    route = respx_mock.post(url).respond(200, json=hosted_completion(model))

    async with provider_pools(settings) as registry:
        assert set(registry.adapters) == {name}
        adapter, resolved = registry.resolve(f"{name}/{model}")
        result = await adapter.chat(
            ChatCompletionRequest.model_validate(
                {"model": f"{name}/{model}", "messages": [{"role": "user", "content": "Hi"}]}
            ),
            resolved,
        )

    assert result.model == f"{name}/{model}"
    assert route.calls.last.request.headers["authorization"] == "Bearer fake-test-key"


async def test_new_providers_own_separate_pools_and_breakers(
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
        _env_file=None,  # pyright: ignore[reportCallIssue]  # disable developer .env
        providers={"zai": {"api_key": "fake-zai"}, "nvidia": {"api_key": "fake-nvidia"}},
    )

    async with provider_pools(settings) as registry:
        service = ResilienceService(registry, load_catalog(), settings.resilience)
        assert len(clients) == 2
        assert clients[0] is not clients[1]
        assert service.breakers["zai"] is not service.breakers["nvidia"]
        assert service.budgets["zai"] is not service.budgets["nvidia"]

    assert all(client.is_closed for client in clients)


def test_all_provider_contracts_are_registered() -> None:
    assert set(ADAPTER_TYPES) == set(get_args(ProviderName))


def test_unpriced_trial_is_listable_but_not_an_alias_candidate() -> None:
    catalog = load_catalog()
    now = datetime(2026, 9, 30, tzinfo=UTC)

    assert "nvidia/moonshotai/kimi-k3" not in available_models(catalog, ["nvidia"], now)
    assert available_models(catalog, ["nvidia"], now, include_unpriced=True) == {
        "nvidia/moonshotai/kimi-k3"
    }
