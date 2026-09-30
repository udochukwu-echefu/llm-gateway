"""Live smoke model selection is independent of gateway routing and the model catalog."""

import os
from dataclasses import dataclass

from llm_gateway.schemas.common import ProviderName


@dataclass(frozen=True)
class LiveProvider:
    name: ProviderName
    chat_model: str
    embedding_model: str | None

    @property
    def deadline_s(self) -> float:
        return 330.0 if self.name == "nvidia" else 60.0

    @property
    def request_timeout_s(self) -> float:
        return self.deadline_s + 30.0 if self.name == "nvidia" else self.deadline_s + 5.0


NVIDIA_KIMI = LiveProvider("nvidia", "moonshotai/kimi-k3", None)
NVIDIA_GLM_FLASH = LiveProvider("nvidia", "z-ai/glm-5.3-flash", None)


PROVIDERS = (
    LiveProvider("groq", "openai/gpt-oss-20b", None),
    LiveProvider("deepseek", "deepseek-flash", None),
    LiveProvider("gemini", "gemini-3.8-flash", "gemini-embedding-2"),
    LiveProvider("openai", "gpt-4.1-nano", "text-embedding-3-small"),
    LiveProvider("zai", "glm-5.3-flash", None),
    NVIDIA_KIMI,
    NVIDIA_GLM_FLASH,
)


def resolve_live_models(provider: LiveProvider) -> LiveProvider:
    prefix = f"GATEWAY_LIVE_{provider.name.upper()}_"
    return LiveProvider(
        provider.name,
        os.environ.get(prefix + "CHAT_MODEL") or provider.chat_model,
        os.environ.get(prefix + "EMBEDDING_MODEL") or provider.embedding_model,
    )
