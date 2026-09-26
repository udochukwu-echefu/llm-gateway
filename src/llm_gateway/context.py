"""Facts about the current request (model, token counts, ...) that belong in its access log.

`annotate()` also binds them to structlog, so every later log line carries them. The dict
is needed as well: a streamed response body runs in a child task, which receives a *copy*
of the context. Values bound there never reach the middleware, but changes to a shared
dict do.
"""

from contextvars import ContextVar, Token
from typing import Any

import structlog

_fields: ContextVar[dict[str, Any] | None] = ContextVar("request_log_fields", default=None)


def begin_request() -> tuple[dict[str, Any], Token[dict[str, Any] | None]]:
    fields: dict[str, Any] = {}
    return fields, _fields.set(fields)


def end_request(token: Token[dict[str, Any] | None]) -> None:
    _fields.reset(token)


def annotate(**fields: Any) -> None:
    current = _fields.get()
    if current is not None:
        current.update(fields)
    structlog.contextvars.bind_contextvars(**fields)
