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
from llm_gateway.schemas.common import ProviderName


class GeminiAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    capabilities = Capabilities(
        supports_embeddings=True,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=True,
    )
