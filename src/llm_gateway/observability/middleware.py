"""Measure the response boundary without buffering SSE or labelling arbitrary paths."""

import time

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from llm_gateway.observability.tracing import ProviderWait, Telemetry, current, provider_wait

ROUTES = frozenset({"/v1/chat/completions", "/v1/embeddings", "/v1/models", "/healthz", "/readyz"})


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, telemetry: Telemetry) -> None:
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route = scope["path"] if scope["path"] in ROUTES else "other"
        token = current.set(self.telemetry)
        wait = ProviderWait()
        wait_token = provider_wait.set(wait)
        parent = TraceContextTextMapPropagator().extract(dict(Headers(scope=scope)))
        try:
            with self.telemetry.tracer.start_as_current_span(
                f"request {route}",
                context=parent,
                kind=trace.SpanKind.SERVER,
                attributes={"http.route": route},
                record_exception=False,
                set_status_on_exception=False,
            ) as active:
                await self._request(scope, receive, send, route, wait, active)
        finally:
            provider_wait.reset(wait_token)
            current.reset(token)

    async def _request(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        route: str,
        wait: ProviderWait,
        active: trace.Span,
    ) -> None:
        metrics = self.telemetry.metrics
        started = time.perf_counter()
        status, streaming = 500, False
        first: float | None = None
        first_wait = 0.0
        metrics.inflight.labels(route).inc()

        async def observe(message: Message) -> None:
            nonlocal status, streaming, first, first_wait
            if message["type"] == "http.response.start":
                status = message["status"]
                streaming = (
                    Headers(scope=message).get("content-type", "").startswith("text/event-stream")
                )
            elif message["type"] == "http.response.body" and message.get("body") and first is None:
                first, first_wait = time.perf_counter(), wait.seconds
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            elapsed = time.perf_counter() - started
            overhead = elapsed - wait.seconds
            if streaming and first is not None:
                metrics.ttfb.labels(route).observe(first - started)
                overhead = first - started - first_wait
            metrics.overhead.labels(route).observe(max(0, overhead))
            metrics.duration.labels(route).observe(elapsed)
            metrics.requests.labels(route, f"{status // 100}xx").inc()
            metrics.inflight.labels(route).dec()
            active.set_attribute("http.response.status_code", status)
            if status >= 500:
                active.set_status(trace.StatusCode.ERROR)
