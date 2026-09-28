"""Real inference, with a transport spy that inspects bodies and never credentials."""

import httpx
import pytest

from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.guardrails.fixtures import EMAIL
from tests.live.models import LiveProvider

pytestmark = pytest.mark.live


@pytest.mark.parametrize(
    "live_guardrail_policy", [GuardrailPolicy((("email", "redact"),))], indirect=True
)
async def test_live_email_redaction_and_restore(
    live_provider: LiveProvider, live_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = httpx.AsyncHTTPTransport.handle_async_request
    inspected: list[bool] = []

    async def spy(transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        inspected.append(EMAIL.encode() not in body and b"[EMAIL_1]" in body)
        return await original(transport, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", spy)
    response = await live_client.post(
        "/v1/chat/completions",
        json={
            "model": f"{live_provider.name}/{live_provider.chat_model}",
            "messages": [
                {
                    "role": "user",
                    "content": "Repeat exactly this sentence, preserving all bracketed "
                    f"placeholders literally: Hello {EMAIL}.",
                }
            ],
        },
        headers={"x-lgw-cache": "disabled"},
    )

    assert inspected
    assert all(inspected)
    assert response.status_code == 200, f"{live_provider.name} returned HTTP {response.status_code}"
    assert EMAIL in response.json()["choices"][0]["message"]["content"]
