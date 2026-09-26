from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from llm_gateway.config import Settings
from llm_gateway.errors import GatewayError
from llm_gateway.upstream import UpstreamClient, UpstreamStreamingResponse, transport_error

router = APIRouter()


class ChatCompletionRequest(BaseModel):
    """The minimum the gateway must understand to proxy a request.

    Step 2 replaces this with the full canonical schema. Until then unknown fields are
    allowed, and the client's original bytes are forwarded untouched.
    """

    model_config = ConfigDict(extra="allow", strict=True)

    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness only: the process is up. It deliberately does not call the provider."""
    return {"status": "ok"}


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    upstream: UpstreamClient = request.app.state.upstream

    body = await _read_json_body(request, settings.max_request_bytes)
    payload = _parse(body)
    # Bound here so the access log line and every later log line include them.
    structlog.contextvars.bind_contextvars(model=payload.model, stream=payload.stream)

    response = await upstream.open_chat_completion(body)
    # The provider's own ID for this call, for correlating with them when something breaks.
    structlog.contextvars.bind_contextvars(upstream_request_id=response.headers.get("x-request-id"))

    if payload.stream:
        return UpstreamStreamingResponse(response)

    try:
        content = await response.aread()
    except httpx.HTTPError as exc:
        raise transport_error(exc) from exc
    finally:
        await response.aclose()
    return Response(content, media_type="application/json")


async def _read_json_body(request: Request, limit: int) -> bytes:
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


def _parse(body: bytes) -> ChatCompletionRequest:
    try:
        return ChatCompletionRequest.model_validate_json(body)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'body'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)[:5]
        )
        raise GatewayError(
            400,
            f"Invalid request body. {problems}",
            type="invalid_request_error",
            code="invalid_body",
        ) from None
