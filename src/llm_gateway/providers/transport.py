from collections.abc import Callable
from typing import Any

import httpx
import structlog
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from pydantic import ValidationError

from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.observability.tracing import current
from llm_gateway.schemas.common import ResponseModel
from llm_gateway.usage.binding import mark_connect_failed, mark_rejected, mark_sent

log = structlog.get_logger("llm_gateway.upstream")


class UpstreamClient:
    """HTTP transport and ADR 0002 error mapping shared by compatible adapters."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        request_id_header: str | None,
        map_status: Callable[[httpx.Response], GatewayError] | None = None,
    ) -> None:
        self._http = http
        self._request_id_header = request_id_header
        self._map_status = map_status or status_error

    async def open(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        """POST `payload` and return the response with its body still unread.

        The caller owns the returned response and must close it. Error statuses are
        read, closed and raised as GatewayError here, so the caller only sees successes.
        """
        request = self._http.build_request("POST", path, json=payload)
        telemetry = current.get()
        if telemetry is not None and telemetry.propagate:
            carrier: dict[str, str] = {}
            TraceContextTextMapPropagator().inject(carrier)
            request.headers.update(carrier)
        mark_sent()
        try:
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as exc:
            if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
                mark_connect_failed()
            raise transport_error(exc) from exc

        log.debug("upstream_response", status=response.status_code)
        annotate(
            upstream_request_id=(
                response.headers.get(self._request_id_header) if self._request_id_header else None
            )
        )
        if response.is_error:
            mark_rejected()
            try:
                await response.aread()
            except httpx.HTTPError as exc:
                raise transport_error(exc) from exc
            finally:
                await response.aclose()
            error = self._map_status(response)
            error.upstream_status = response.status_code
            if error.code != "upstream_account_error" and (
                retry_after := response.headers.get("retry-after")
            ):
                error.headers["retry-after"] = retry_after
            raise error
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
            transport_kind=type(exc).__name__,
        )
    if isinstance(exc, httpx.TimeoutException):
        return GatewayError(
            504,
            "The model provider did not respond in time.",
            type="upstream_error",
            code="upstream_timeout",
            transport_kind=type(exc).__name__,
        )
    return GatewayError(
        502,
        "The model provider could not be reached.",
        type="upstream_error",
        code="upstream_unavailable",
        transport_kind=type(exc).__name__,
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


class _ProviderProblem(ResponseModel):
    """NVIDIA also documents RFC 7807 problem details for rejected requests."""

    type: str
    status: int
    detail: str


def _upstream_message(response: httpx.Response) -> str | None:
    for shape in (_ProviderError, _ProviderError.Detail, _ProviderProblem):
        try:
            parsed = shape.model_validate_json(response.content)
        except ValidationError:
            continue
        if isinstance(parsed, _ProviderError):
            return parsed.error.message
        if isinstance(parsed, _ProviderError.Detail):
            return parsed.message
        if parsed.status == response.status_code:
            return parsed.detail
    return None
