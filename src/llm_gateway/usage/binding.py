"""Share the current billing event with transport without exposing HTTP internals."""

from contextvars import ContextVar, Token

from llm_gateway.usage.record import UsageEvent

_current: ContextVar[UsageEvent | None] = ContextVar("usage_event", default=None)


def bind(event: UsageEvent) -> Token[UsageEvent | None]:
    return _current.set(event)


def unbind(token: Token[UsageEvent | None]) -> None:
    _current.reset(token)


def mark_sent() -> None:
    event = _current.get()
    if event is not None:
        event.sent = True


def mark_rejected() -> None:
    event = _current.get()
    if event is not None:
        event.provider_rejected = True
