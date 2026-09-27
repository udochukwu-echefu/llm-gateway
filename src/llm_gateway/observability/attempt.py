"""Keep one client span per attempt alive through stream consumption."""

import time
from collections.abc import Awaitable

from opentelemetry import trace
from opentelemetry.trace import Span

from llm_gateway.observability.tracing import current, provider_wait
from llm_gateway.schemas.chat import Usage
from llm_gateway.usage.record import UsageEvent


class AttemptObservation:
    def __init__(self, event: UsageEvent, retry: bool) -> None:
        self.event = event
        self.telemetry = current.get()
        self.started = time.perf_counter()
        self.ended = False
        tracer = self.telemetry.tracer if self.telemetry else trace.NoOpTracer()
        provider = event.price.provider
        self.span: Span = tracer.start_span(
            f"{event.endpoint} {event.price.model}",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "gen_ai.operation.name": event.endpoint,
                "gen_ai.provider.name": "gcp.gemini" if provider == "gemini" else provider,
                "gen_ai.request.model": event.price.model,
                "lgw.attempt": event.attempt,
                "lgw.retry": retry,
                "lgw.fallback": event.fallback_from is not None,
            },
        )

    async def wait[T](self, operation: Awaitable[T]) -> T:
        started = time.perf_counter()
        try:
            with trace.use_span(
                self.span, end_on_exit=False, record_exception=False, set_status_on_exception=False
            ):
                return await operation
        finally:
            timing = provider_wait.get()
            if timing is not None:
                timing.seconds += time.perf_counter() - started

    def finish(self) -> None:
        if self.ended:
            return
        self.ended = True
        event = self.event
        self.span.set_attribute("http.response.status_code", event.status_code)
        self.span.set_attribute("lgw.outcome", event.outcome)
        if event.usage is not None:
            self.span.set_attribute("gen_ai.usage.input_tokens", event.usage.prompt_tokens)
            if isinstance(event.usage, Usage):
                self.span.set_attribute("gen_ai.usage.output_tokens", event.usage.completion_tokens)
        if event.outcome != "success":
            self.span.set_status(trace.StatusCode.ERROR)
        self.span.end()
        if self.telemetry is not None and event.sent:
            metrics = self.telemetry.metrics
            metrics.upstream_requests.labels(
                event.price.provider, event.price.model, event.outcome, event.alias or ""
            ).inc()
            metrics.upstream_duration.labels(event.price.provider).observe(
                time.perf_counter() - self.started
            )
