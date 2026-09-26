from fastapi import Request
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from llm_gateway.catalog import ModelPrice
from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import GatewayState
from llm_gateway.schemas.chat import Usage
from llm_gateway.schemas.common import ProviderName, RequestModel
from llm_gateway.schemas.embeddings import EmbeddingUsage

MAX_REPORTED_PROBLEMS = 5


async def read_json_body(request: Request, limit: int) -> bytes:
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise GatewayError(
            415,
            "Content-Type must be application/json.",
            type="invalid_request_error",
            code="unsupported_media_type",
        )

    too_large = GatewayError(
        413,
        f"Request body exceeds {limit} bytes.",
        type="invalid_request_error",
        code="request_too_large",
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large

    # Content-Length can be absent (chunked) or wrong, so enforce the limit while reading.
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def parse_request[M: RequestModel](model: type[M], body: bytes) -> M:
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_input=False, include_context=False)
        problems = "; ".join(_describe(error) for error in errors[:MAX_REPORTED_PROBLEMS])
        raise GatewayError(
            400,
            f"Invalid request body. {problems}",
            type="invalid_request_error",
            code="invalid_body",
        ) from None


def _describe(error: ErrorDetails) -> str:
    location = ".".join(str(part) for part in error["loc"]) or "body"
    if error["type"] == "extra_forbidden":
        return (
            f"{location}: unknown field. Provider-specific fields go in "
            "provider_options.<provider>."
        )
    return f"{location}: {error['msg'].removeprefix('Value error, ')}"


def record_usage(usage: Usage | EmbeddingUsage | None) -> None:
    """Put token counts in the access log. Step 5 turns these into cost records."""
    if usage is None:
        return
    if isinstance(usage, EmbeddingUsage):
        annotate(prompt_tokens=usage.prompt_tokens, total_tokens=usage.total_tokens)
        return
    annotate(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cached_tokens=usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens,
        reasoning_tokens=(
            usage.completion_tokens_details and usage.completion_tokens_details.reasoning_tokens
        ),
    )


def require_price(state: GatewayState, provider: ProviderName, model: str, kind: str) -> ModelPrice:
    price = state.catalog.find(provider, model, kind)
    if price is None:
        raise GatewayError(
            404,
            f"Model '{provider}/{model}' is not in this gateway's catalogue.",
            type="invalid_request_error",
            code="model_not_found",
        )
    return price
