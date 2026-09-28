import json
from collections.abc import Callable

import httpx

from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.api.conftest import ResilientApp
from tests.fixtures import sse
from tests.guardrails.fixtures import EMAIL, OTHER_EMAIL, chunks, prompt


async def test_stream_tool_arguments_and_choices_restore_independently(
    resilient: ResilientApp, set_guardrails: Callable[[GuardrailPolicy], None]
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    events = chunks(["[EMA", "IL_1]"])
    for event, part in zip(events, ['{"email":"[E', 'MAIL_2]"}', ""], strict=True):
        event["choices"].append(
            {
                "index": 1,
                "delta": {"tool_calls": [{"index": 4, "function": {"arguments": part}}]},
                "finish_reason": "tool_calls" if not part else None,
            }
        )
    resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(sse(*events, "[DONE]")),
        )
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json=prompt(f"{EMAIL} {OTHER_EMAIL}", stream=True)
    )

    data = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")
    ]
    text = "".join(
        c["delta"].get("content", "") for event in data for c in event["choices"] if c["index"] == 0
    )
    arguments = "".join(
        tool["function"].get("arguments", "")
        for event in data
        for c in event["choices"]
        if c["index"] == 1
        for tool in c["delta"].get("tool_calls", [])
    )
    assert text == EMAIL
    assert json.loads(arguments) == {"email": OTHER_EMAIL}


async def test_stream_flushes_unfinished_placeholder_at_done(
    resilient: ResilientApp, set_guardrails: Callable[[GuardrailPolicy], None]
) -> None:
    set_guardrails(GuardrailPolicy((("email", "redact"),)))
    events = chunks(["literal [EMA"])[:-1]
    resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"".join(sse(*events, "[DONE]")),
        )
    )

    response = await resilient.client.post("/v1/chat/completions", json=prompt(EMAIL, stream=True))

    data = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")
    ]
    assert (
        "".join(c["delta"].get("content", "") for event in data for c in event["choices"])
        == "literal [EMA"
    )
