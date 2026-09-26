"""OpenAI compatibility, checked 2026-09-26.

https://platform.openai.com/docs/api-reference/chat/create verifies developer,
max_completion_tokens, include_usage and all canonical chat parameters.
https://platform.openai.com/docs/api-reference/embeddings/create verifies embeddings,
token inputs and optional embedding parameters, plus https://api.openai.com/v1.
https://platform.openai.com/docs/api-reference/introduction documents x-request-id.
Capabilities describe the endpoint; individual model restrictions remain provider errors.
No separate Chat Completions reasoning text is documented, so do not manufacture it.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.common import ProviderName


class OpenAIAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "openai"
    base_url = "https://api.openai.com/v1"
    capabilities = Capabilities(
        supports_embeddings=True,
        supports_stream_usage=True,
        supports_developer=True,
        supports_max_completion_tokens=True,
    )
