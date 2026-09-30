"""NVIDIA hosted Kimi-K3 compatibility, verified 2026-09-30.

https://build.nvidia.com/moonshotai/kimi-k3 verifies the integrate API endpoint;
https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer verifies
https://integrate.api.nvidia.com/v1 and exact model ID moonshotai/kimi-k3.
Its Role enum documents system/user/assistant/tool: translate developer to system.
max_tokens is documented; max_completion_tokens is not explicitly unsupported,
so forward both unchanged. stream_options "such as include_usage" and canonical
prompt/completion/total usage in responses and streams are documented.
Rejection quote (temperature description): "the other sampling parameters
(top_p, presence_penalty, frequency_penalty, n) are fixed by the model and are not
exposed." Reject them, including n=1 and explicit nulls. Message content quote:
"For system and assistant roles, the object list format is not supported."
Reject those arrays after role translation. Undocumented options (including
response_format and tool_choice) are forwarded, not rejected from schema absence.
https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3 verifies 1,048,576
context, tools, structured output, low/high/max reasoning effort, Global geography,
and complete assistant-history replay including reasoning_content and tool_calls.
The infer schema documents typed request reasoning_content, while response/delta
schemas lag the model card. Preserve canonical reasoning_content when returned;
never extract think tags. No alternate cache-token shape verified: preserve
canonical cached_tokens if present; absent details remain unknown.
Only Kimi chat is in scope; its endpoint inventory has no embeddings: reject it.
Use documented NVCF-REQID for provider request IDs.
Trial terms (sections 1.2/1.4), verified from the official PDF:
https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf
prohibit production without a separate subscription and permit deducted/purchased
credits. No per-token $0 guarantee: catalogue price is unknown, not zero.
Numeric rate limits and free prototyping are not established by these terms;
the trial/use limits are verified, a specific free allowance is not.
"""

from typing import Any

from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.common import ProviderName


class NvidiaAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "nvidia"
    request_id_header = "nvcf-reqid"
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=True,
        unsupported_parameters=frozenset({"top_p", "presence_penalty", "frequency_penalty", "n"}),
    )

    def _translate_messages(self, payload: dict[str, Any]) -> None:
        super()._translate_messages(payload)
        for message in payload["messages"]:
            if message["role"] in ("system", "assistant") and isinstance(
                message.get("content"), list
            ):
                raise self.unsupported(f"messages[{message['role']}].content (object list)")
