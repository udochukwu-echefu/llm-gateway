import json
import logging
from typing import cast

import httpx
import pytest
import respx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.main import create_app
from tests.conftest import UPSTREAM_KEY, MemoryKeyRepository, OfflineLimitService
from tests.fixtures import CHAT_REQUEST, COMPLETION


@pytest.mark.parametrize("propagate", [False, True])
async def test_span_tree_genai_privacy_and_propagation(
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
    capsys: pytest.CaptureFixture[str],
    propagate: bool,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    settings.log_format = "json"
    settings.tracing.propagate_to_providers = propagate
    app = create_app(
        settings,
        key_repository=memory_repository,
        catalog=test_catalog,
        limit_service=OfflineLimitService(),
        tracer_provider=provider,
    )
    secret_prompt = "sentinel-prompt-never-export"
    completion = {
        **COMPLETION,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "sentinel-completion-never-export"},
                "finish_reason": "stop",
            }
        ],
    }

    def respond(request: httpx.Request) -> httpx.Response:
        logging.getLogger("uvicorn.error").info("attempt_stdlib")
        return httpx.Response(200, json=completion)

    route = upstream.post("/chat/completions").mock(side_effect=respond)
    trace_id = "1234567890abcdef1234567890abcdef"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.post(
            "/v1/chat/completions",
            json={**CHAT_REQUEST, "messages": [{"role": "user", "content": secret_prompt}]},
            headers={
                "authorization": f"Bearer {issued_test_key}",
                "traceparent": f"00-{trace_id}-1234567890abcdef-01",
            },
        )
    spans = exporter.get_finished_spans()
    provider.shutdown()

    assert response.status_code == 200
    assert {s.name for s in spans} == {
        "request /v1/chat/completions",
        "authenticate",
        "limits.admission",
        "chat llama-3.3-70b-versatile",
        "usage.enqueue",
    }
    server = next(s for s in spans if s.kind == SpanKind.SERVER)
    attempt = next(s for s in spans if s.kind == SpanKind.CLIENT)
    assert server.context is not None
    assert server.context.trace_id == int(trace_id, 16)
    assert server.parent is not None
    assert server.parent.span_id == int("1234567890abcdef", 16)
    assert all(
        s.parent is not None and s.parent.span_id == server.context.span_id
        for s in spans
        if s is not server
    )
    attrs = attempt.attributes or {}
    assert attrs["gen_ai.provider.name"] == "groq"
    assert attrs["gen_ai.request.model"] == "llama-3.3-70b-versatile"
    assert attrs["gen_ai.response.model"] == COMPLETION["model"]
    assert attrs["gen_ai.usage.input_tokens"] == 9
    assert attrs["gen_ai.usage.output_tokens"] == 1
    assert attrs["lgw.attempt"] == 1
    assert attrs["lgw.retry"] is False
    assert attrs["lgw.fallback"] is False
    assert ("traceparent" in cast(httpx.Request, route.calls[0][0]).headers) is propagate
    if propagate:
        assert trace_id in cast(httpx.Request, route.calls[0][0]).headers["traceparent"]
    captured = capsys.readouterr()
    exported = repr([(s.name, dict(s.attributes or {}), s.events, s.status) for s in spans])
    for secret in (
        secret_prompt,
        "sentinel-completion-never-export",
        UPSTREAM_KEY,
        issued_test_key,
    ):
        assert secret not in exported
        assert secret not in captured.out + captured.err
    logs = [json.loads(line) for line in (captured.out + captured.err).splitlines() if line]
    correlated = next(line for line in logs if line.get("event") == "attempt_stdlib")
    assert correlated["trace_id"] == trace_id
    assert (
        correlated["span_id"] == format(attempt.context.span_id, "016x")
        if attempt.context
        else False
    )
