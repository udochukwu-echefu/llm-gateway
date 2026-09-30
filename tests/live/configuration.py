"""Live gateway profiles accommodate queued NVIDIA calls without relaxing every provider."""

from llm_gateway.config import ProvidersSettings, Settings
from tests.live.models import LiveProvider


def smoke_settings(provider: LiveProvider, block: dict[str, str]) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # live tests use environment only
        providers=ProvidersSettings.model_validate({provider.name: block}),
        usage_batch_size=1,
        resilience={"deadline_s": provider.deadline_s},
    )
