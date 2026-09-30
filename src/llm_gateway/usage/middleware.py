"""Finalize provider-bound accounting after the response completes or fails."""

import asyncio
import time
from contextlib import suppress

import anyio
import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from llm_gateway.guardrails.session import GuardrailSession
from llm_gateway.usage.finalization import finalize_usage

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
                response_status: int = message["status"]
                status = response_status
                for key, value in scope.get("state", {}).get("limit_headers", {}).items():
                    if response_status >= 400:
                        # A GatewayError may already carry these admission headers.
                        MutableHeaders(scope=message)[key] = value
                    else:
                        MutableHeaders(scope=message).append(key, value)
            elif message["type"] == "http.response.body" and first_byte_at is None:
                first_byte_at = time.perf_counter()
            await send(message)

        try:
            await self.app(scope, receive, send_with_usage)
        finally:
            guardrails = scope.get("state", {}).get("guardrails")
            if isinstance(guardrails, GuardrailSession):
                guardrails.report()
            heartbeat = scope.get("state", {}).get("limit_heartbeat")
            if isinstance(heartbeat, asyncio.Task):
                heartbeat.cancel()
                with anyio.CancelScope(shield=True), suppress(asyncio.CancelledError):
                    await heartbeat
            await finalize_usage(scope, started, first_byte_at, status)
