"""Live smoke model selection is independent of gateway routing and the model catalog."""

import os
from dataclasses import dataclass

from llm_gateway.schemas.common import ProviderName


@dataclass(frozen=True)
class LiveProvider:
    name: ProviderName
    chat_model: str
    embedding_model: str | None


PROVIDERS = (
    LiveProvider("groq", "openai/gpt-oss-20b", None),
    LiveProvider("deepseek", "deepseek-flash", None),
    LiveProvider("gemini", "gemini-3.8-flash", "gemini-embedding-001"),
    LiveProvider("openai", "gpt-4.1-nano", "text-embedding-3-small"),
)


def resolve_live_models(provider: LiveProvider) -> LiveProvider:
    prefix = f"GATEWAY_LIVE_{provider.name.upper()}_"
    return LiveProvider(
        provider.name,
        os.environ.get(prefix + "CHAT_MODEL") or provider.chat_model,
        os.environ.get(prefix + "EMBEDDING_MODEL") or provider.embedding_model,
    )
