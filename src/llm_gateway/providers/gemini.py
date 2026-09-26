"""Gemini OpenAI compatibility, checked 2026-09-26.

https://ai.google.dev/gemini-api/docs/openai verifies the base URL, embeddings,
stream_options.include_usage (extra_body example), tools, structured output,
reasoning_effort and service_tier. System instructions are documented; developer is not,
so translate to system. Undocumented parameters, including both token-limit spellings
and embedding options, are forwarded unchanged; absence is not evidence of non-support.
Use the shared x-request-id convention when present; no different header is documented.
No separate reasoning output representation was verified: no mapping.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk
from llm_gateway.schemas.common import ProviderName


class GeminiAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "gemini"
    capabilities = Capabilities(
        supports_embeddings=True,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=True,
    )

    def normalize_chat(self, result: ChatCompletion | ChatCompletionChunk) -> None:
        super().normalize_chat(result)
        usage = result.usage
        if usage is None:
            return
        # Gemini's OpenAI surface can omit thinking from completion_tokens while
        # total_tokens includes it; output pricing includes thinking tokens. Do not
        # claim the entire difference is reasoning without a provider breakdown.
        unaccounted = usage.total_tokens - usage.prompt_tokens - usage.completion_tokens
        if unaccounted > 0:
            usage.completion_tokens += unaccounted
