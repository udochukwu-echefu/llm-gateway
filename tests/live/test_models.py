"""Offline unit tests for smoke-test configuration; no live marker or provider calls."""

import pytest

from tests.live.configuration import smoke_settings
from tests.live.models import (
    NVIDIA_GLM_FLASH,
    NVIDIA_KIMI,
    PROVIDERS,
    LiveProvider,
    resolve_live_models,
)


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda provider: provider.name)
@pytest.mark.parametrize("value", [None, ""])
def test_unset_or_empty_overrides_use_defaults(
    monkeypatch: pytest.MonkeyPatch,
    provider: LiveProvider,
    value: str | None,
) -> None:
    for suffix in ("CHAT_MODEL", "EMBEDDING_MODEL"):
        variable = f"GATEWAY_LIVE_{provider.name.upper()}_{suffix}"
        if value is None:
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, value)

    assert resolve_live_models(provider) == provider


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda provider: provider.name)
@pytest.mark.parametrize(
    ("suffix", "field"),
    [
        ("CHAT_MODEL", "chat_model"),
        ("EMBEDDING_MODEL", "embedding_model"),
    ],
)
def test_each_live_model_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
    provider: LiveProvider,
    suffix: str,
    field: str,
) -> None:
    monkeypatch.setenv(f"GATEWAY_LIVE_{provider.name.upper()}_{suffix}", "vendor/replacement")

    result = resolve_live_models(provider)

    assert getattr(result, field) == "vendor/replacement"
    assert result.name == provider.name
    assert getattr(provider, field) != "vendor/replacement"


def test_groq_default_exercises_slashes_in_provider_model_ids() -> None:
    provider = next(provider for provider in PROVIDERS if provider.name == "groq")

    assert provider.chat_model == "openai/gpt-oss-20b"
    assert f"{provider.name}/{provider.chat_model}" == "groq/openai/gpt-oss-20b"


def test_nvidia_flash_is_a_separate_smoke_target_next_to_kimi() -> None:
    index = PROVIDERS.index(NVIDIA_KIMI)

    assert PROVIDERS[index + 1] == NVIDIA_GLM_FLASH
    assert NVIDIA_GLM_FLASH.chat_model == "z-ai/glm-5.3-flash"


@pytest.mark.parametrize("provider", [NVIDIA_KIMI, NVIDIA_GLM_FLASH])
def test_nvidia_live_deadline_and_outer_timeout_cover_free_tier_queue(
    provider: LiveProvider,
) -> None:
    settings = smoke_settings(provider, {"api_key": "fake-test-key"})

    assert provider.deadline_s == 330
    assert provider.request_timeout_s == 360
    timeouts = settings.provider_timeouts("nvidia", settings.providers.nvidia)
    assert timeouts.read == 300
    assert provider.request_timeout_s > settings.resilience.deadline_s > timeouts.read
    assert settings.resilience.retry_read_timeouts is False


def test_other_live_providers_keep_shorter_request_deadlines() -> None:
    for provider in PROVIDERS:
        if provider.name != "nvidia":
            assert provider.deadline_s == 60
            assert provider.request_timeout_s == 65
