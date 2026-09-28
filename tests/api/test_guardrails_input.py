import json
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, EMBEDDINGS
from tests.guardrails.fixtures import (
    CARD,
    CARD_CONTEXTS,
    EMAIL,
    FAKE_GATEWAY_KEY,
    FAKE_KEY,
    FAKE_PRIVATE_KEY,
    IBAN,
    OTHER_EMAIL,
    prompt,
)

SetGuardrails = Callable[[GuardrailPolicy], None]


@pytest.mark.parametrize("secret", [FAKE_KEY, FAKE_GATEWAY_KEY, FAKE_PRIVATE_KEY])
async def test_default_secret_block_has_no_values_calls_or_receipts(
    resilient: ResilientApp, secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = get_app_state(resilient.app)
    assert state.limits is not None
    rpm = AsyncMock(return_value={})
    monkeypatch.setattr(state.limits, "request_admission", rpm)

    response = await resilient.client.post("/v1/chat/completions", json=prompt(secret))
    await state.usage_writer.stop()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "guardrail_blocked"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert "secret_" in response.json()["error"]["message"]
    assert secret not in response.text
    assert not resilient.router.calls
    assert not resilient.records
    rpm.assert_not_awaited()


@pytest.mark.parametrize("role", ["system", "developer", "user", "assistant", "tool"])
@pytest.mark.parametrize("parts", [False, True])
async def test_every_message_role_is_scanned(
    resilient: ResilientApp, role: str, parts: bool
) -> None:
    message = {"role": role, "content": [{"type": "text", "text": FAKE_KEY}] if parts else FAKE_KEY}
    if role == "tool":
        message["tool_call_id"] = "fake-call"

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "messages": [message]}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "guardrail_blocked"
    assert not resilient.router.calls


async def test_tool_results_are_scanned(resilient: ResilientApp) -> None:
    body = {
        **CHAT_REQUEST,
        "messages": [{"role": "tool", "tool_call_id": "fake", "content": FAKE_KEY}],
    }

    response = await resilient.client.post("/v1/chat/completions", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "guardrail_blocked"


async def test_escaped_tool_arguments_are_scanned(resilient: ResilientApp) -> None:
    escaped = "".join(f"\\u{ord(char):04x}" for char in FAKE_KEY)
    body = {
        **CHAT_REQUEST,
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "fake",
                        "type": "function",
                        "function": {"name": "fake", "arguments": '{"model":"' + escaped + '"}'},
                    }
                ],
            }
        ],
    }

    response = await resilient.client.post("/v1/chat/completions", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "guardrail_blocked"


async def test_embeddings_are_redacted_before_provider(
    resilient: ResilientApp, set_guardrails: SetGuardrails
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    route = resilient.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)

    response = await resilient.client.post(
        "/v1/embeddings", json={"model": "openai/embedding", "input": [EMAIL, EMAIL, OTHER_EMAIL]}
    )

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)["input"] == [
        "[EMAIL_1]",
        "[EMAIL_1]",
        "[EMAIL_2]",
    ]


@pytest.mark.parametrize(("text", "sensitive"), [(CARD, CARD), (IBAN, IBAN), *CARD_CONTEXTS])
async def test_payment_data_is_redacted_by_default(
    resilient: ResilientApp, text: str, sensitive: str
) -> None:
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt(text))

    assert response.status_code == 200
    assert sensitive not in json.loads(route.calls.last.request.content)["messages"][0]["content"]
    assert "_1]" in json.loads(route.calls.last.request.content)["messages"][0]["content"]


async def test_organization_block_cannot_be_loosened_by_team(
    resilient: ResilientApp, set_guardrails: SetGuardrails
) -> None:
    set_guardrails(GuardrailPolicy((("email", "block"),), (("email", "allow"),)))

    response = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL))

    assert response.status_code == 400
    assert not resilient.router.calls


@pytest.mark.parametrize("field", ["extra_text", "file", "model"])
async def test_nested_provider_options_are_scanned(resilient: ResilientApp, field: str) -> None:
    body = {**prompt("safe"), "provider_options": {"groq": {"extra_text": {field: FAKE_KEY}}}}

    response = await resilient.client.post("/v1/chat/completions", json=body)

    assert response.status_code == 400
    assert not resilient.router.calls


async def test_tool_descriptions_are_scanned(resilient: ResilientApp) -> None:
    body = {
        **prompt("safe"),
        "tools": [{"type": "function", "function": {"name": "fake", "description": FAKE_KEY}}],
    }

    response = await resilient.client.post("/v1/chat/completions", json=body)

    assert response.status_code == 400
    assert not resilient.router.calls


async def test_guardrail_changes_use_original_key_cache_ttl(
    resilient: ResilientApp, set_guardrails: SetGuardrails
) -> None:
    state = get_app_state(resilient.app)
    state.key_cache.clock = resilient.time.clock
    state.key_cache.ttl = 30
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )
    first = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL))
    set_guardrails(GuardrailPolicy((("email", "block"),)))
    resilient.time.now = 29

    cached = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL))
    resilient.time.now = 30
    denied = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL))

    assert first.status_code == cached.status_code == 200
    assert denied.status_code == 400
    assert route.call_count == 2


@pytest.mark.parametrize(
    "text", ["Meeting on 2026-09-28", "Meeting on 28/09/2026", "At 12:34", "We sold 1234567 units"]
)
async def test_phone_redaction_preserves_dates_times_and_plain_counts(
    resilient: ResilientApp, set_guardrails: SetGuardrails, text: str
) -> None:
    set_guardrails(GuardrailPolicy((("phone", "redact"),)))
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(
        200, json=COMPLETION
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt(text))

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)["messages"][0]["content"] == text
