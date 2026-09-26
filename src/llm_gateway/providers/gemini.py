"""Gemini OpenAI compatibility, checked 2026-09-26.

https://ai.google.dev/gemini-api/docs/openai verifies the base URL, embeddings,
stream_options.include_usage (extra_body example), tools, structured output,
reasoning_effort and service_tier. System instructions are documented; developer is not,
so translate to system. Token-limit spellings and other parameters below were not
verified in this guide: reject rather than assume a safe token-limit translation.
Embedding token IDs, dimensions, encoding_format and user were not verified: reject.
No request-ID header or separate reasoning output representation was verified: no mapping.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.common import ProviderName


class GeminiAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    capabilities = Capabilities(
        supports_embeddings=True,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=False,
        supports_token_inputs=False,
        unsupported_parameters=frozenset(
            {
                "max_tokens",
                "max_completion_tokens",
                "seed",
                "logprobs",
                "top_logprobs",
                "logit_bias",
                "frequency_penalty",
                "presence_penalty",
                "parallel_tool_calls",
                "user",
                "safety_identifier",
                "temperature",
                "top_p",
                "stop",
                "messages[].name",
            }
        ),
        unsupported_embedding_parameters=frozenset({"dimensions", "encoding_format", "user"}),
    )
