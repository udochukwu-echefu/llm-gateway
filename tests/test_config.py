import os

import pytest
from pydantic import SecretStr, ValidationError

from llm_gateway.config import ProviderSettings, ProvidersSettings, Settings
from llm_gateway.main import create_app
from tests.conftest import TEST_DATABASE_URL, TEST_PEPPER, MemoryKeyRepository


def test_base_url_is_optional_without_populating_defaults() -> None:
    providers = ProvidersSettings.model_validate({"groq": {"api_key": "fake-key"}})

    assert ProviderSettings().base_url is None
    assert ProviderSettings(base_url=None).base_url is None
    assert providers.groq.base_url is None


@pytest.fixture(autouse=True)
def clean_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in os.environ:
        if name.startswith("GATEWAY_PROVIDERS"):
            monkeypatch.delenv(name)


def test_no_enabled_provider_fails_startup() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime settings option


def test_nested_environment_enables_only_keyed_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__API_KEY", "fake-key")
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__BASE_URL", "https://custom.test/v1")
    monkeypatch.setenv("GATEWAY_PROVIDERS__GEMINI__BASE_URL", "https://disabled.test/v1")

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime settings option

    assert [name for name, _ in settings.providers.enabled()] == ["groq"]
    assert str(settings.providers.groq.base_url) == "https://custom.test/v1"
    assert "fake-key" not in repr(settings)


@pytest.mark.parametrize("value", ["", " "])
def test_empty_keys_fail_startup(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__API_KEY", value)

    with pytest.raises(ValidationError, match="nonempty"):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime settings option


@pytest.mark.parametrize(
    "url", ["not-a-url", "ftp://example.com", "https://u:p@host/v1", "https://host/?key=x"]
)
def test_invalid_base_urls_fail_startup(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__API_KEY", "fake-key")
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__BASE_URL", url)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime settings option


def test_missing_redis_url_fails_app_startup_without_localhost_fallback(
    settings: Settings,
    memory_repository: MemoryKeyRepository,
) -> None:
    class Store:
        def get(self, name: str) -> SecretStr | None:
            values = {
                "api_key_pepper": TEST_PEPPER,
                "database_url": TEST_DATABASE_URL,
                "providers__groq__api_key": "fake-provider-key",
            }
            return SecretStr(values[name]) if name in values else None

    with pytest.raises(ValueError, match="GATEWAY_REDIS_URL is required"):
        create_app(settings, key_repository=memory_repository, secret_store=Store())
