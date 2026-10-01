import pytest
from pydantic import SecretStr, ValidationError

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.secrets import EnvSecretStore
from tests.conftest import MemoryKeyRepository, OfflineLimitService


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://api.openai.com/v1",
        "http://localhost:8000/v1",
        "http://127.0.0.1:18000/evil",
        "http://fake-provider:8000/v1",
    ],
)
def test_demo_guard_rejects_non_fake_urls(url: str | None) -> None:
    with pytest.raises(ValidationError, match="Demo deployment permits only"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]  # never read local .env
            demo_deployment=True,
            providers={"openai": {"api_key": "fake", "base_url": url}},
        )


def test_demo_guard_allows_exact_compose_service() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # never read local .env
        demo_deployment=True,
        providers={"groq": {"api_key": "fake", "base_url": "http://127.0.0.1:18000/v1"}},
    )
    settings.validate_demo_providers()


def test_demo_guard_rechecks_file_resolved_provider(
    settings: Settings, memory_repository: MemoryKeyRepository
) -> None:
    configured = settings.model_copy(update={"demo_deployment": True})
    with pytest.raises(ValueError, match="Demo deployment permits only"):
        create_app(
            configured,
            key_repository=memory_repository,
            limit_service=OfflineLimitService(),
            secret_store=EnvSecretStore(
                {"providers__groq__api_key": SecretStr("fake-resolved-key")}
            ),
        )
