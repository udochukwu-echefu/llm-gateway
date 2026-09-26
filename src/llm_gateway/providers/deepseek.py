"""DeepSeek compatibility, checked 2026-09-26.

https://api-docs.deepseek.com/ documents https://api.deepseek.com; the spec's /v1
alias could not be reverified in the current guide and is retained as required.
https://api-docs.deepseek.com/api/create-chat-completion documents system (not developer),
max_tokens (not max_completion_tokens), include_usage and reasoning_content.
Translate developer to system and the token limit to max_tokens. Penalties are explicitly
unsupported. Rejection evidence from that reference:
frequency_penalty and presence_penalty: "This parameter is no longer supported. It will
not take effect if you pass it to the API."
response_format.type: "Must be one of `text` or `json_object`."
Embeddings are rejected because no embeddings endpoint exists in the official API reference
at https://api-docs.deepseek.com/api/create-chat-completion (endpoint inventory).
The token-limit conflict is a gateway translation ambiguity, not a provider restriction.
Undocumented parameters are forwarded. Use the shared x-request-id convention when present;
no different request-ID header is documented.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk, PromptTokensDetails
from llm_gateway.schemas.common import ProviderName


class DeepSeekAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "deepseek"
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=False,
        supports_json_schema=False,
        unsupported_parameters=frozenset(
            {
                "frequency_penalty",
                "presence_penalty",
            }
        ),
    )

    def normalize_chat(self, result: ChatCompletion | ChatCompletionChunk) -> None:
        super().normalize_chat(result)
        usage = result.usage
        if usage is None:
            return
        extras = usage.model_extra or {}
        hits = extras.pop("prompt_cache_hit_tokens", None)
        extras.pop("prompt_cache_miss_tokens", None)
        if isinstance(hits, int) and (
            usage.prompt_tokens_details is None or usage.prompt_tokens_details.cached_tokens is None
        ):
            usage.prompt_tokens_details = PromptTokensDetails(cached_tokens=hits)
