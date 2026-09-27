import asyncio
from collections.abc import AsyncIterator

import httpx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from llm_gateway.gateway_state import get_app_state
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, STREAM, USAGE_CHUNK, sse


class DelayedStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        for payload in sse(*STREAM, USAGE_CHUNK, "[DONE]"):
            await asyncio.sleep(0.025)
            yield payload


async def test_stream_span_includes_final_usage_and_overhead_stops_at_first_byte(
    resilient: ResilientApp,
) -> None:
    telemetry = get_app_state(resilient.app).telemetry
    assert telemetry is not None
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.tracer = provider.get_tracer("test")
    resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, stream=DelayedStream())
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    )
    provider.shutdown()

    assert response.status_code == 200
    assert "[DONE]" in response.text
    spans = exporter.get_finished_spans()
    attempts = [s for s in spans if s.kind == SpanKind.CLIENT]
    assert len(attempts) == 1
    attempt = attempts[0]
    assert (attempt.attributes or {})["gen_ai.usage.output_tokens"] == 2
    assert (attempt.attributes or {})["lgw.outcome"] == "success"
    assert attempt.end_time is not None
    assert attempt.start_time is not None
    assert (attempt.end_time - attempt.start_time) / 1e9 >= 0.1
    metrics = telemetry.metrics.registry
    labels = {"route": "/v1/chat/completions"}
    first = metrics.get_sample_value("lgw_time_to_first_byte_seconds_sum", labels)
    duration = metrics.get_sample_value("lgw_request_duration_seconds_sum", labels)
    overhead = metrics.get_sample_value("lgw_gateway_overhead_seconds_sum", labels)
    assert first is not None
    assert duration is not None
    assert overhead is not None
    assert duration - first >= 0.075
    assert first - overhead >= 0.025
    assert metrics.get_sample_value("lgw_time_to_first_byte_seconds_count", labels) == 1


async def test_each_retry_has_its_own_client_span(resilient: ResilientApp) -> None:
    telemetry = get_app_state(resilient.app).telemetry
    assert telemetry is not None
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.tracer = provider.get_tracer("test")
    resilient.router.post("https://groq.test/v1/chat/completions").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=COMPLETION)]
    )

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    provider.shutdown()

    assert response.status_code == 200
    attempts = [s for s in exporter.get_finished_spans() if s.kind == SpanKind.CLIENT]
    assert [(s.attributes or {})["lgw.attempt"] for s in attempts] == [1, 2]
    assert [(s.attributes or {})["lgw.retry"] for s in attempts] == [False, True]
    assert attempts[0].status.status_code == StatusCode.ERROR
    assert attempts[1].status.status_code != StatusCode.ERROR
    assert attempts[0].parent == attempts[1].parent
