"""Z.ai international Model API compatibility, verified 2026-09-30.

https://docs.z.ai/guides/overview/quick-start verifies api.z.ai/api/paas/v4,
not the separate Coding Plan endpoint or BigModel China platform.
https://docs.z.ai/guides/vlm/glm-5.3-flash verifies lowercase glm-5.3-flash
and glm-5.3-flashx; https://docs.z.ai/api-reference/llm/chat-completion
verifies glm-5.3, max_tokens, the system/user/assistant/tool role enum,
reasoning_content and prompt_tokens_details.cached_tokens. Translate developer
to system. Both token-limit spellings are forwarded: max_completion_tokens is
undocumented, not explicitly unsupported. Cached tokens/reasoning already use
canonical fields; do not parse think tags or invent token breakdowns.
Rejection evidence: response_format.type enum is "text", "json_object";
thinking.type for GLM-5.3/Flash "can only be enabled". Other model-specific
constraints remain provider errors (stop's prose and schema disagree).
https://docs.z.ai/llms.txt lists no international embeddings endpoint: reject it.
https://docs.z.ai/guides/capabilities/streaming verifies final-chunk usage and
delta.reasoning_content. stream_options.include_usage is not documented there;
forward it under the unknown-parameter rule, without promising it takes effect.
All other canonical parameters and serving-provider options are forwarded.
Preserve typed assistant reasoning for clear_thinking=false, documented by the
chat reference. Shared x-request-id is read if present; no alternate header verified.
https://docs.z.ai/guides/overview/pricing verifies list USD/1M input/cache/output:
Flash 0.15/0.03/0.50, FlashX 0.37/0.075/1.25, GLM-5.3 1.4/0.26/4.4.
Promotion end 2026-09-09: reviewer-verified 2026-09-30, not re-verified by agent;
the current pricing page shows the list rates, not the promotion history.
https://docs.z.ai/legal-agreement/privacy-policy API DPA section 3 verifies
Customer Data is generally processed in Singapore (sg), not an exclusive guarantee.
https://docs.z.ai/api-reference/api-code distinguishes business codes from HTTP status:
1113: "Insufficient balance or no resource package. Please recharge."
1302: "Rate limit reached for requests"
1305: "The service may be temporarily overloaded, please try again later"
Billing/quota/account 429 codes are 1113, 1308 (usage allowance), 1309 (expired
Coding Plan), 1310 (weekly/monthly allowance), 1311 (model entitlement), 1313
(fair-usage account restriction), 1314 (expired enterprise package), 1315 (wrong
key product), 1316/1317 (allowance plus insufficient balance), 1318-1321
(allowance plus monthly spend cap). Map these to non-retryable generic 502s.
1302/1305 retain retry/429 handling; unknown codes retain the shared mapping.
Authentication codes 1000/1001/1003/1005 and permission code 1220 already use
the shared sanitized 401/403-to-502 mapping, without retries.
"""

from typing import Any, cast

import httpx
import structlog
from pydantic import ValidationError

from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName, ResponseModel

ACCOUNT_CODES = frozenset(
    {
        "1113",
        "1308",
        "1309",
        "1310",
        "1311",
        "1313",
        "1314",
        "1315",
        "1316",
        "1317",
        "1318",
        "1319",
        "1320",
        "1321",
    }
)
log = structlog.get_logger("llm_gateway.upstream")


class ZaiAdapter(OpenAICompatibleAdapter):
    name: ProviderName = "zai"
    capabilities = Capabilities(
        supports_embeddings=False,
        supports_stream_usage=True,
        supports_developer=False,
        supports_max_completion_tokens=True,
        supports_json_schema=False,
    )

    def _status_error(self, response: httpx.Response) -> GatewayError:
        try:
            business_code = _ZaiError.model_validate_json(response.content).error.code
        except ValidationError:
            return super()._status_error(response)
        if response.status_code != 429 or business_code not in ACCOUNT_CODES:
            return super()._status_error(response)
        log.error(
            "upstream_account_error",
            provider=self.name,
            upstream_status=response.status_code,
            business_code=business_code,
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
        thinking = payload.get("thinking")
        if (
            model in ("glm-5.3", "glm-5.3-flash", "glm-5.3-flashx")
            and isinstance(thinking, dict)
            and cast(dict[str, Any], thinking).get("type") == "disabled"
        ):
            raise self.unsupported("thinking.type=disabled")
        return payload


class _ZaiError(ResponseModel):
    class Detail(ResponseModel):
        code: str

    error: Detail
