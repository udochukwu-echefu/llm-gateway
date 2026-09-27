"""Finalize provider-bound accounting after the response completes or fails."""

import asyncio
import time
from contextlib import suppress

import anyio
import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from llm_gateway.gateway_state import get_app_state
from llm_gateway.usage.record import UsageEvent

log = structlog.get_logger("llm_gateway.usage")


class UsageMiddleware:
    """Observe ASGI messages without buffering streams or delaying a response for storage."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        first_byte_at: float | None = None
        status: int | None = None

        async def send_with_usage(message: Message) -> None:
            nonlocal status, first_byte_at
            if message["type"] == "http.response.start":
                status = message["status"]
                for key, value in scope.get("state", {}).get("limit_headers", {}).items():
                    MutableHeaders(scope=message).append(key, value)
            elif message["type"] == "http.response.body" and first_byte_at is None:
                first_byte_at = time.perf_counter()
            await send(message)

        try:
            await self.app(scope, receive, send_with_usage)
        finally:
            heartbeat = scope.get("state", {}).get("limit_heartbeat")
            if isinstance(heartbeat, asyncio.Task):
                heartbeat.cancel()
                with anyio.CancelScope(shield=True), suppress(asyncio.CancelledError):
                    await heartbeat
            event = scope.get("state", {}).get("usage_event")
            record = None
            if isinstance(event, UsageEvent) and event.sent:
                try:
                    event.status_code = status or 500
                    record = event.finish(
                        _elapsed_ms(started, time.perf_counter()),
                        _elapsed_ms(started, first_byte_at),
                    )
                except Exception:
                    log.exception("usage_enqueue_failed", request_id=event.request_id)
            admitted = scope.get("state", {}).get("limit_admission")
            if admitted is not None:
                team, lease, limits = admitted
                service = get_app_state(scope["app"]).limits
                if service is not None:
                    try:
                        with anyio.CancelScope(shield=True):
                            await service.finish(team, lease, record, limits)
                    except Exception:
                        log.exception("limits_finalize_failed")
            if record is not None:
                try:
                    get_app_state(scope["app"]).usage_writer.enqueue(record)
                except Exception:
                    log.exception("usage_enqueue_failed", request_id=record.request_id)


def _elapsed_ms(start: float, end: float | None) -> float | None:
    return None if end is None else round((end - start) * 1000, 2)
