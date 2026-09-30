"""The slowest enabled provider sets the lease floor, including file-backed keys."""

import pytest
from pydantic import SecretStr

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from tests.conftest import TEST_DATABASE_URL, TEST_PEPPER, MemoryKeyRepository, OfflineLimitService


@pytest.mark.parametrize("phase", ["connect", "read", "write", "pool"])
def test_provider_override_larger_than_lease_fails_startup(phase: str) -> None:
    with pytest.raises(ValueError, match=r"Lease TTL must exceed.*'nvidia'"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]  # no developer .env
            providers={
                "groq": {"api_key": "fake"},
                "nvidia": {
                    "api_key": "fake",
                    f"{phase}_timeout_s": 1000,
                },
            },
        )


def test_disabled_provider_does_not_raise_lease_floor() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # no developer .env
        providers={"groq": {"api_key": "fake"}, "nvidia": {"read_timeout_s": 1000}},
        limits={"lease_ttl_s": 100},
    )

    assert [name for name, _ in settings.providers.enabled()] == ["groq"]


def test_lease_uses_largest_combined_provider_not_independent_phase_maxima() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # no developer .env
        providers={
            "groq": {"api_key": "fake", "connect_timeout_s": 200, "read_timeout_s": 10},
            "openai": {"api_key": "fake", "connect_timeout_s": 10, "read_timeout_s": 200},
        },
        limits={"lease_ttl_s": 226},
    )

    assert (
        max(
            settings.provider_timeouts(name, block).combined
            for name, block in settings.providers.enabled()
        )
        == 225
    )


def test_nvidia_default_read_timeout_requires_a_longer_lease() -> None:
    with pytest.raises(ValueError, match=r"'nvidia'.*320 s"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]  # no developer .env
            providers={"nvidia": {"api_key": "fake"}},
            limits={"lease_ttl_s": 320},
        )


def test_secret_store_enabled_provider_rechecks_timeouts_before_pool_creation(
    settings: Settings,
    memory_repository: MemoryKeyRepository,
) -> None:
    settings.providers.nvidia.read_timeout_s = 1000

    class Store:
        def get(self, name: str) -> SecretStr | None:
            values = {
                "api_key_pepper": TEST_PEPPER,
                "database_url": TEST_DATABASE_URL,
                "providers__nvidia__api_key": "fake",
            }
            return SecretStr(values[name]) if name in values else None

    with pytest.raises(ValueError, match=r"Lease TTL must exceed.*'nvidia'"):
        create_app(
            settings,
            key_repository=memory_repository,
            secret_store=Store(),
            limit_service=OfflineLimitService(),
        )
