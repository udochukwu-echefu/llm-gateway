"""Manual spans deliberately omit bodies, headers and exception messages."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Tracer
from structlog.typing import EventDict

from llm_gateway.observability.configuration import TracingSettings
from llm_gateway.observability.metrics import Metrics


@dataclass
class Telemetry:
    metrics: Metrics
    tracer: Tracer
    propagate: bool = False


@dataclass
class ProviderWait:
    seconds: float = 0.0


current: ContextVar[Telemetry | None] = ContextVar("telemetry", default=None)
provider_wait: ContextVar[ProviderWait | None] = ContextVar("provider_wait", default=None)


def make_provider(settings: TracingSettings) -> TracerProvider | None:
    if settings.otlp_endpoint is None:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": "llm-gateway"}),
        sampler=ParentBased(TraceIdRatioBased(settings.sample_ratio)),
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=str(settings.otlp_endpoint)))
    )
    return provider


@contextmanager
def span(name: str) -> Generator[Span]:
    telemetry = current.get()
    tracer = telemetry.tracer if telemetry else trace.NoOpTracer()
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as active:
        try:
            yield active
        except BaseException:
            active.set_status(trace.StatusCode.ERROR)
            raise


def trace_fields(logger: object, method: str, fields: EventDict) -> EventDict:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        fields["trace_id"] = format(context.trace_id, "032x")
        fields["span_id"] = format(context.span_id, "016x")
    return fields
