import json
from collections.abc import Callable

import httpx
import pytest

from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.api.conftest import ResilientApp
from tests.fixtures import sse
from tests.guardrails.fixtures import CARD, EMAIL, FAKE_KEY, OTHER_EMAIL, chunks, completion, prompt

SetGuardrails = Callable[[GuardrailPolicy], None]


async def test_nonstream_restores_consistent_request_placeholders(
    resilient: ResilientApp, set_guardrails: SetGuardrails
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion("[EMAIL_1] [EMAIL_2] [EMAIL_1]")
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json=prompt(f"{EMAIL} {OTHER_EMAIL} {EMAIL}")
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == f"{EMAIL} {OTHER_EMAIL} {EMAIL}"
    assert (
        json.loads(route.calls.last.request.content)["messages"][0]["content"]
        == "[EMAIL_1] [EMAIL_2] [EMAIL_1]"
    )


async def test_user_placeholder_is_reserved_not_confused_with_redaction(
    resilient: ResilientApp, set_guardrails: SetGuardrails
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion("[EMAIL_1] [EMAIL_2]")
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json=prompt(f"[EMAIL_1] {EMAIL}")
    )

    assert (
        json.loads(route.calls.last.request.content)["messages"][0]["content"]
        == "[EMAIL_1] [EMAIL_2]"
    )
    assert response.json()["choices"][0]["message"]["content"] == f"[EMAIL_1] {EMAIL}"


async def test_new_output_pii_is_masked_without_restoring_it(resilient: ResilientApp) -> None:
    resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion(CARD)
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt("safe"))

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "[OUTPUT_CARD_NUMBER_1]"
    assert CARD not in response.text


async def test_new_output_secret_is_blocked(resilient: ResilientApp) -> None:
    resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=completion(FAKE_KEY)
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt("safe"))

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "guardrail_blocked_output"
    assert FAKE_KEY not in response.text


@pytest.mark.parametrize(
    "parts",
    [
        ["[EMA", "IL_1]"],
        ["[E", "MAIL_", "1]"],
        ["[", "EMAIL_1", "]"],
        ["[EMAIL_1]"],
        ["[EMAIL_1] tail [", "no"],
    ],
)
@pytest.mark.parametrize("field", ["content", "reasoning_content", "refusal"])
async def test_stream_restores_split_placeholders(
    resilient: ResilientApp, set_guardrails: SetGuardrails, parts: list[str], field: str
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    route = resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(sse(*chunks(parts, field), "[DONE]")),
        )
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL, stream=True))

    data = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")
    ]
    text = "".join(c["delta"].get(field, "") for event in data for c in event.get("choices", []))
    assert text == "".join(parts).replace("[EMAIL_1]", EMAIL)
    assert EMAIL.encode() not in route.calls.last.request.content
    assert response.text.endswith("data: [DONE]\n\n")


async def test_stream_output_is_detect_only_even_across_chunks(resilient: ResilientApp) -> None:
    parts = [FAKE_KEY[:8], FAKE_KEY[8:]]
    resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(sse(*chunks(parts), "[DONE]")),
        )
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt("safe", stream=True))

    data = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")
    ]
    assert (
        "".join(c["delta"].get("content", "") for event in data for c in event["choices"])
        == FAKE_KEY
    )
    telemetry = get_app_state(resilient.app).telemetry
    assert telemetry is not None
    assert (
        telemetry.metrics.registry.get_sample_value(
            "lgw_guardrail_findings_total",
            {"direction": "output", "detector": "secret_api_key", "action": "block"},
        )
        == 1
    )
