from collections.abc import AsyncIterator, Callable
from typing import Any

import anyio
import httpx
import structlog
from pydantic import ValidationError
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from llm_gateway.errors import GatewayError
from llm_gateway.schemas.common import ResponseModel
from llm_gateway.sse import encode_error

log = structlog.get_logger("llm_gateway.upstream")

# Turns the provider's raw stream into the bytes we send to the client.
StreamTransform = Callable[[AsyncIterator[bytes]], AsyncIterator[bytes]]


class UpstreamClient:
    """Sends requests to a single OpenAI-compatible provider.

    Step 3 replaces this with provider adapters behind a common interface. The error
    mapping here (docs/adr/0002) carries over to them.
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def open(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        """POST `payload` and return the response with its body still unread.

        The caller owns the returned response and must close it. Error statuses are
        read, closed and raised as GatewayError here, so the caller only sees successes.
        """
        request = self._http.build_request("POST", path, json=payload)
        try:
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise transport_error(exc) from exc

        log.debug("upstream_response", status=response.status_code)
        if response.is_error:
            try:
                await response.aread()
            except httpx.HTTPError as exc:
                raise transport_error(exc) from exc
            finally:
                await response.aclose()
            raise status_error(response)
        return response


async def read_model[M: ResponseModel](response: httpx.Response, model: type[M]) -> M:
    """Read a whole (non-streamed) response body and check it has the shape we rely on."""
    try:
        content = await response.aread()
    except httpx.HTTPError as exc:
        raise transport_error(exc) from exc
    finally:
        await response.aclose()
    try:
        return model.model_validate_json(content)
    except ValidationError as exc:
        raise invalid_response(exc) from None


def invalid_response(exc: ValidationError) -> GatewayError:
    # Log where the shape was wrong, never the content: it may contain the completion.
    log.error(
        "upstream_invalid_response",
        problems=[".".join(str(part) for part in error["loc"]) for error in exc.errors()][:5],
    )
    return GatewayError(
        502,
        "The model provider returned an unexpected response.",
        type="upstream_error",
        code="upstream_invalid_response",
    )


def transport_error(exc: httpx.HTTPError) -> GatewayError:
    log.warning("upstream_transport_error", error=type(exc).__name__)
    if isinstance(exc, httpx.PoolTimeout):
        # Every upstream connection is busy: we are saturated, the provider may be fine.
        return GatewayError(
            503,
            "The gateway is at capacity. Retry shortly.",
            type="server_error",
            code="gateway_overloaded",
        )
    if isinstance(exc, httpx.TimeoutException):
        return GatewayError(
            504,
            "The model provider did not respond in time.",
            type="upstream_error",
            code="upstream_timeout",
        )
    return GatewayError(
        502,
        "The model provider could not be reached.",
        type="upstream_error",
        code="upstream_unavailable",
    )


def status_error(response: httpx.Response) -> GatewayError:
    status = response.status_code
    log.warning("upstream_error_status", upstream_status=status)

    if status == 429:
        retry_after = response.headers.get("retry-after")
        return GatewayError(
            429,
            _upstream_message(response) or "The model provider is rate limiting requests.",
            type="rate_limit_error",
            code="upstream_rate_limited",
            headers={"retry-after": retry_after} if retry_after else None,
        )
    if status in (401, 403):
        # Our provider credentials are wrong. The client's request is fine, so this must not
        # look like a client auth failure, and the provider's message is not theirs to see.
        log.error("upstream_auth_failed", upstream_status=status)
        return GatewayError(
            502,
            "The gateway could not authenticate with the model provider.",
            type="upstream_error",
            code="upstream_auth_failed",
        )
    if status == 408:
        return GatewayError(
            504,
            "The model provider timed out.",
            type="upstream_error",
            code="upstream_timeout",
        )
    if 400 <= status < 500:
        # A problem with the request itself (unknown model, bad parameter, context too long).
        # The provider's message is what the client needs to fix it.
        return GatewayError(
            status,
            _upstream_message(response) or "The model provider rejected the request.",
            type="invalid_request_error",
            code="upstream_rejected_request",
        )
    return GatewayError(
        502,
        "The model provider returned an error.",
        type="upstream_error",
        code="upstream_server_error",
    )


class _ProviderError(ResponseModel):
    class Detail(ResponseModel):
        message: str

    error: Detail


def _upstream_message(response: httpx.Response) -> str | None:
    try:
        return _ProviderError.model_validate_json(response.content).error.message
    except ValidationError:
        return None


class UpstreamStreamingResponse(StreamingResponse):
    """Relays an upstream server-sent-events stream to the client, chunk by chunk.

    The upstream connection is always released when this response ends, including when
    the client disconnects mid-stream. Otherwise we would keep the connection open and
    keep paying for tokens nobody will read.
    """

    def __init__(self, upstream: httpx.Response, transform: StreamTransform) -> None:
        self._upstream = upstream
        self._transform = transform
        super().__init__(
            self._relay(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    async def _relay(self) -> AsyncIterator[bytes]:
        try:
            # aiter_bytes, not aiter_raw: raw bytes may still be gzip-encoded.
            async for chunk in self._transform(self._upstream.aiter_bytes()):
                yield chunk
        except httpx.HTTPError as exc:
            # Headers and a 200 are already sent, so the status can't change. Emit an error
            # event (OpenAI SDKs raise on it) instead of silently truncating the stream.
            log.warning("upstream_stream_interrupted", error=type(exc).__name__)
            yield encode_error(transport_error(exc))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._upstream.aclose()
