"""Environment overrides must reach separate HTTP pools, not just configuration DTOs."""

import pytest
import respx
from pydantic import ValidationError

from llm_gateway.config import ProviderSettings, Settings
from llm_gateway.providers.pools import provider_pools
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.providers.fixtures import hosted_completion


@pytest.mark.parametrize("phase", ["connect", "read", "write", "pool"])
async def test_nested_environment_override_reaches_only_its_provider_pool(
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
    phase: str,
) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__API_KEY", "fake-groq")
    monkeypatch.setenv("GATEWAY_PROVIDERS__NVIDIA__API_KEY", "fake-nvidia")
    monkeypatch.setenv(f"GATEWAY_PROVIDERS__NVIDIA__{phase.upper()}_TIMEOUT_S", "123")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # never read developer .env
    groq = respx_mock.post("https://api.groq.com/openai/v1/chat/completions").respond(
        200, json=hosted_completion("openai/gpt-oss-20b")
    )
    nvidia = respx_mock.post("https://integrate.api.nvidia.com/v1/chat/completions").respond(
        200, json=hosted_completion("moonshotai/kimi-k3")
    )

    async with provider_pools(settings) as registry:
        for model in ("groq/openai/gpt-oss-20b", "nvidia/moonshotai/kimi-k3"):
            adapter, resolved = registry.resolve(model)
            await adapter.chat(
                ChatCompletionRequest.model_validate(
                    {"model": model, "messages": [{"role": "user", "content": "Hi"}]}
                ),
                resolved,
            )

    assert groq.calls.last.request.extensions["timeout"] == {
        "connect": 5.0,
        "read": 60.0,
        "write": 10.0,
        "pool": 5.0,
    }
    expected = {"connect": 5.0, "read": 300.0, "write": 10.0, "pool": 5.0, phase: 123.0}
    assert nvidia.calls.last.request.extensions["timeout"] == expected


def test_unset_timeouts_inherit_globals_except_nvidia_read(settings: Settings) -> None:
    settings.connect_timeout_s, settings.read_timeout_s = 7, 80
    settings.write_timeout_s, settings.pool_timeout_s = 11, 9
    unset = ProviderSettings()

    names: tuple[ProviderName, ...] = ("groq", "deepseek", "gemini", "openai", "zai")
    for name in names:
        effective = settings.provider_timeouts(name, unset)
        assert (effective.connect, effective.read, effective.write, effective.pool) == (
            7,
            80,
            11,
            9,
        )
    assert settings.provider_timeouts("nvidia", unset).read == 300
    assert settings.provider_timeouts("nvidia", ProviderSettings(read_timeout_s=42)).read == 42


@pytest.mark.parametrize("phase", ["connect", "read", "write", "pool"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_provider_timeouts_must_be_positive_and_finite(phase: str, value: float) -> None:
    with pytest.raises(ValidationError, match=f"{phase}_timeout_s"):
        ProviderSettings.model_validate({f"{phase}_timeout_s": value})
