"""Groq compatibility, checked 2026-09-26.

https://console.groq.com/docs/openai verifies the base URL, name/logprob restrictions and n=1.
https://console.groq.com/docs/api-reference (including its embedded OpenAPI schema)
verifies developer, max_completion_tokens and stream_options.include_usage support,
and unsupported penalties. Rejection evidence:
https://console.groq.com/docs/openai: "The following fields are currently not supported
and will result in a 400 error (yikes) if they are supplied:" lists logprobs, logit_bias,
top_logprobs and messages[].name. "If N is supplied, it must be equal to 1."
https://console.groq.com/docs/api-reference says for frequency_penalty and presence_penalty:
"This is not yet supported by any of our models."
Embeddings are rejected because no embeddings endpoint exists in that API's endpoint
inventory. Undocumented parameters such as safety_identifier are forwarded unchanged.
https://console.groq.com/docs/reasoning documents message.reasoning.
https://github.com/groq/groq-python/blob/main/src/groq/types/chat/chat_completion_chunk.py
documents delta.reasoning. Raw think tags are deliberately not parsed.
Use the shared x-request-id header convention when present; no different header is documented.
"""

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.defaults import DEFAULT_BASE_URLS
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk, Delta, ResponseMessage
from llm_gateway.schemas.common import ProviderName


class GroqAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "groq"
    base_url = DEFAULT_BASE_URLS["groq"]
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=True,
        supports_max_completion_tokens=True,
        supports_multiple_choices=False,
        unsupported_parameters=frozenset(
            {
                "logprobs",
                "top_logprobs",
                "logit_bias",
                "messages[].name",
                "frequency_penalty",
                "presence_penalty",
            }
        ),
    )

    def normalize_chat(self, result: ChatCompletion | ChatCompletionChunk) -> None:
        super().normalize_chat(result)
        if isinstance(result, ChatCompletion):
            for choice in result.choices:
                _normalize_reasoning(choice.message)
        if isinstance(result, ChatCompletionChunk):
            for choice in result.choices:
                _normalize_reasoning(choice.delta)


def _normalize_reasoning(message: ResponseMessage | Delta) -> None:
    extras = message.model_extra
    if extras and "reasoning" in extras:
        reasoning = extras.get("reasoning")
        if isinstance(reasoning, str) or reasoning is None:
            extras.pop("reasoning")
            if "reasoning_content" not in message.model_fields_set:
                message.reasoning_content = reasoning
