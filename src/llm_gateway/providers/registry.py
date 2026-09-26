from typing import get_args

from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import ProviderAdapter
from llm_gateway.providers.deepseek import DeepSeekAdapter
from llm_gateway.providers.gemini import GeminiAdapter
from llm_gateway.providers.groq import GroqAdapter
from llm_gateway.providers.openai import OpenAIAdapter
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.common import ProviderName

ADAPTER_TYPES: dict[ProviderName, type[OpenAICompatibleAdapter]] = {
    "groq": GroqAdapter,
    "deepseek": DeepSeekAdapter,
    "gemini": GeminiAdapter,
    "openai": OpenAIAdapter,
}


class ProviderRegistry:
    def __init__(self, adapters: list[ProviderAdapter]) -> None:
        self.adapters = {adapter.name: adapter for adapter in adapters}

    def resolve(self, model: str) -> tuple[ProviderAdapter, str]:
        provider, separator, provider_model = model.partition("/")
        if not separator:
            reason = "Model must have a '<provider>/<model>' prefix"
        elif provider not in get_args(ProviderName):
            reason = f"Unknown provider '{provider}'"
        elif provider not in self.adapters:
            reason = f"Provider '{provider}' is not configured on this gateway"
        elif not provider_model.strip():
            reason = f"Missing model name for provider '{provider}'"
        else:
            return self.adapters[provider], provider_model
        configured = ", ".join(sorted(self.adapters)) or "none"
        raise GatewayError(
            404,
            f"{reason}. Configured providers: {configured}.",
            type="invalid_request_error",
            code="model_not_found",
        )
