"""NVIDIA hosted Kimi-K3 and GLM compatibility, verified 2026-09-30.

https://build.nvidia.com/moonshotai/kimi-k3 verifies the integrate API endpoint;
https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-infer verifies
https://integrate.api.nvidia.com/v1 and exact model ID moonshotai/kimi-k3.
Its Role enum documents system/user/assistant/tool: translate developer to system.
max_tokens is documented; max_completion_tokens is not explicitly unsupported,
so forward both unchanged. stream_options "such as include_usage" and canonical
prompt/completion/total usage in responses and streams are documented.
Rejection quote (temperature description): "the other sampling parameters
(top_p, presence_penalty, frequency_penalty, n) are fixed by the model and are not
exposed." Reject them for Kimi only, including n=1 and explicit nulls. Message content quote:
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
Kimi's content-array restriction is also model-specific, not a GLM restriction.
https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-infer and
https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash-infer include request
examples with exact IDs z-ai/glm-5.3 and z-ai/glm-5.3-flash. Both references document
top_p, frequency_penalty and presence_penalty; do not inherit Kimi's exclusions.
Other absent fields remain forwarded under the unknown-parameter rule, including
stream_options, tools and reasoning (model cards describe tools and reasoning).
The GLM references' role is an unrestricted string, so preserve developer there;
Kimi still translates developer from its explicit role enum. Both GLM model cards
say "Global" and link the same trial terms, not Z.ai's international API rates.
Their 402 PaymentRequiredError example is "You have reached your limit of credits."
Map NVIDIA 402 to sanitized, non-retryable upstream_account_error.
All three models have chat, not embeddings endpoints: reject embeddings.
Use documented NVCF-REQID for provider request IDs.
Kimi's infer reference explicitly documents 202: "Result is pending. Client should
poll using the requestId." NVCF-REQID is "requestId required for pooling" [sic].
https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-statuspolling documents
GET https://integrate.api.nvidia.com/v1/status/{requestId}, bearer auth, 202 pending
and 200 application/json. Poll non-streaming Kimi only, within the existing total
request deadline, and stop locally on disconnect/cancellation. No remote cancel
endpoint or SSE polling response is documented. GLM references list 200 immediate
JSON/SSE results, 402 and 422, but no queued polling protocol; this is not a blanket
synchronous guarantee for integrate. Unexpected GLM/streaming 202 becomes a clear
retryable upstream_pending_unsupported error, never an empty client 202.
Trial terms (sections 1.2/1.4), verified from the official PDF:
https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf
prohibit production without a separate subscription and permit deducted/purchased
credits. No per-token $0 guarantee: catalogue price is unknown, not zero.
Numeric rate limits and free prototyping are not established by these terms;
the trial/use limits are verified, a specific free allowance is not.
"""

from typing import Any

import httpx
import structlog

from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.nvidia_polling import resolve_pending
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName


class NvidiaAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "nvidia"
    request_id_header = "nvcf-reqid"
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=True,
        supports_max_completion_tokens=True,
    )

    async def _open_chat_response(self, payload: dict[str, Any]) -> httpx.Response:
        response = await super()._open_chat_response(payload)
        return await resolve_pending(self._transport, response, payload)

    def _status_error(self, response: httpx.Response) -> GatewayError:
        if response.status_code != 402:
            return super()._status_error(response)
        structlog.get_logger("llm_gateway.upstream").error(
            "upstream_account_error",
            provider=self.name,
            upstream_status=402,
            action="check_provider_billing_quota_and_entitlements",
        )
        return GatewayError(
            502,
            "The gateway's model provider account is unavailable. Contact the gateway operator.",
            type="upstream_error",
            code="upstream_account_error",
        )

    def _chat_payload(self, request: ChatCompletionRequest, model: str) -> dict[str, Any]:
        payload = super()._chat_payload(request, model)
        if model != "moonshotai/kimi-k3":
            return payload
        self._reject_parameters(
            payload, frozenset({"top_p", "presence_penalty", "frequency_penalty", "n"})
        )
        for message in payload["messages"]:
            if message["role"] == "developer":
                message["role"] = "system"
            if message["role"] in ("system", "assistant") and isinstance(
                message.get("content"), list
            ):
                raise self.unsupported(f"messages[{message['role']}].content (object list)")
        return payload
