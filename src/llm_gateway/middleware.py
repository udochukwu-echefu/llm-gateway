import json
import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from llm_gateway import context
from llm_gateway.errors import error_body

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

log = structlog.get_logger("llm_gateway.access")


class RequestContextMiddleware:
    """Gives every request an ID, binds it to the log context, and writes one access log line.

    Written as plain ASGI rather than BaseHTTPMiddleware so streamed responses pass through
    unbuffered, and so the timings reflect when the last byte actually left the gateway.
    It is also the last line of defence: an unhandled exception becomes an OpenAI-shaped 500
    that still carries the request ID.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        started = time.perf_counter()
        status: int | None = None
        first_byte_at: float | None = None
        completed = False

        async def send_with_context(message: Message) -> None:
            nonlocal status, first_byte_at, completed
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            elif message["type"] == "http.response.body":
                if first_byte_at is None:
                    first_byte_at = time.perf_counter()
                if not message.get("more_body", False):
                    completed = True
            await send(message)

        fields, token = context.begin_request()
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_context)
            except Exception:
                log.exception("unhandled_error")
                if status is None:
                    await _send_internal_error(send_with_context)
            finally:
                log.info(
                    "request",
                    method=scope["method"],
                    # The path only: query strings can carry secrets.
                    path=scope["path"],
                    status=status,
                    duration_ms=_elapsed_ms(started, time.perf_counter()),
                    ttfb_ms=_elapsed_ms(started, first_byte_at),
                    # False means the client went away (or we failed) before the body finished.
                    completed=completed,
                    **fields,
                )
                context.end_request(token)


async def _send_internal_error(send: Send) -> None:
    body = json.dumps(
        error_body("Internal gateway error.", type="server_error", code="internal_error")
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _elapsed_ms(start: float, end: float | None) -> float | None:
    return None if end is None else round((end - start) * 1000, 2)
