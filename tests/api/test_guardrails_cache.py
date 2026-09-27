from collections.abc import Callable

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.api.conftest import MemoryRedis, ResilientApp
from tests.guardrails.fixtures import EMAIL, OTHER_EMAIL, completion, prompt

SetGuardrails = Callable[[GuardrailPolicy], None]


async def test_cache_uses_redacted_request_and_restores_fresh_on_hit(
    cached: tuple[ResilientApp, MemoryRedis], set_guardrails: SetGuardrails
) -> None:
    app, redis = cached
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    route = app.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion("Hello [EMAIL_1]")
    )

    first = await app.client.post(
        "/v1/chat/completions", json=prompt(EMAIL), headers={"x-lgw-cache": "enabled"}
    )
    hit = await app.client.post(
        "/v1/chat/completions", json=prompt(OTHER_EMAIL), headers={"x-lgw-cache": "enabled"}
    )

    assert first.headers["x-lgw-cache"] == "miss"
    assert hit.headers["x-lgw-cache"] == "hit"
    assert first.json()["choices"][0]["message"]["content"] == f"Hello {EMAIL}"
    assert hit.json()["choices"][0]["message"]["content"] == f"Hello {OTHER_EMAIL}"
    assert route.call_count == 1
    cache = get_app_state(app.app).response_cache
    assert cache is not None
    for key, value in redis.values.items():
        plaintext = cache.cipher.open(key, value)
        assert plaintext is not None
        assert b"[EMAIL_1]" in plaintext
        assert EMAIL.encode() not in plaintext
        assert OTHER_EMAIL.encode() not in plaintext


async def test_originals_never_leak_to_logs_spans_metrics_cache_or_usage(
    cached: tuple[ResilientApp, MemoryRedis],
    set_guardrails: SetGuardrails,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app, redis = cached
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    state = get_app_state(app.app)
    telemetry = state.telemetry
    assert telemetry is not None
    telemetry.tracer = provider.get_tracer("guardrail-test")
    app.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion("[EMAIL_1]")
    )

    for email in (EMAIL, OTHER_EMAIL):
        response = await app.client.post(
            "/v1/chat/completions", json=prompt(email), headers={"x-lgw-cache": "enabled"}
        )
        assert response.status_code == 200
    await state.usage_writer.stop()

    spans = exporter.get_finished_spans()
    observations = capsys.readouterr().out
    assert observations.count("guardrail_findings") == 2
    observations += repr([(s.name, s.attributes, s.events) for s in spans])
    observations += generate_latest(telemetry.metrics.registry).decode()
    observations += repr(app.records) + repr(redis.values)
    cache = state.response_cache
    assert cache is not None
    observations += repr([cache.cipher.open(key, value) for key, value in redis.values.items()])
    assert EMAIL not in observations
    assert OTHER_EMAIL not in observations
    assert [r.redaction_count for r in app.records] == [1, 1]
    assert [r.outcome for r in app.records] == ["success", "cache_hit"]
    assert any(
        s.name == "guardrails.input"
        and s.attributes
        and s.attributes.get("lgw.guardrails.email") == 1
        for s in spans
    )
    assert (
        telemetry.metrics.registry.get_sample_value(
            "lgw_guardrail_findings_total",
            {"direction": "input", "detector": "email", "action": "redact"},
        )
        == 2
    )
    provider.shutdown()
