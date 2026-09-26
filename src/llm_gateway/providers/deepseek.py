"""DeepSeek compatibility, checked 2026-09-26.

https://api-docs.deepseek.com/ documents https://api.deepseek.com; the spec's /v1
alias could not be reverified in the current guide and is retained as required.
https://api-docs.deepseek.com/api/create-chat-completion documents system (not developer),
max_tokens (not max_completion_tokens), include_usage and reasoning_content.
Translate developer to system and the token limit to max_tokens. Penalties are explicitly
unsupported; the remaining rejected parameters/embeddings are absent from the API reference.
JSON schema output is absent (only text/json_object); no request-ID header was verified.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.common import ProviderName


class DeepSeekAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "deepseek"
    base_url = "https://api.deepseek.com/v1"
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=False,
        supports_json_schema=False,
        unsupported_parameters=frozenset(
            {
                "n",
                "seed",
                "logit_bias",
                "parallel_tool_calls",
                "service_tier",
                "user",
                "safety_identifier",
                "frequency_penalty",
                "presence_penalty",
            }
        ),
    )
