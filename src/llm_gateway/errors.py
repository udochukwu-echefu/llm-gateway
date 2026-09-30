from collections.abc import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class GatewayError(Exception):
    """An error returned to the client in the OpenAI error envelope.

    Clients built on OpenAI SDKs parse `{"error": {...}}`, so every failure the gateway
    produces, including routing 404s, uses this shape. See docs/adr/0002.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        type: str,
        code: str,
        headers: Mapping[str, str] | None = None,
        upstream_status: int | None = None,
        transport_kind: str | None = None,
        retry_allowed: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.type = type
        self.code = code
        self.headers = dict(headers or {})
        self.upstream_status = upstream_status
        self.transport_kind = transport_kind
        self.retry_allowed = retry_allowed


def error_body(message: str, *, type: str, code: str) -> dict[str, dict[str, str | None]]:
    return {"error": {"message": message, "type": type, "param": None, "code": code}}


def error_response(error: GatewayError) -> JSONResponse:
    return JSONResponse(
        error_body(error.message, type=error.type, code=error.code),
        status_code=error.status_code,
        headers=error.headers,
    )


async def gateway_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, GatewayError):  # registered for GatewayError only
        raise exc
    return error_response(exc)


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for HTTPException only
        raise exc
    return JSONResponse(
        error_body(str(exc.detail), type="invalid_request_error", code=f"http_{exc.status_code}"),
        status_code=exc.status_code,
        headers=exc.headers,
    )
