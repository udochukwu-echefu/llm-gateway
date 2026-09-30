import asyncio
import json
from dataclasses import replace

import pytest
import respx

from llm_gateway.guardrails.policy import GuardrailPolicy
from tests.conftest import MemoryKeyRepository
from tests.fixtures import parse_events, sse
from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import HISTORY, NVIDIA_MODELS, hosted_completion, hosted_stream

pytestmark = pytest.mark.parametrize("provider_name", ["nvidia"])
MODEL = "moonshotai/kimi-k3"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("model", NVIDIA_MODELS)
async def test_nested_model_reasoning_and_unknown_cost_receipt(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, stream: bool, model: str
) -> None:
    route = upstream.post("/chat/completions")
    if stream:
        route.respond(200, content=b"".join(sse(*hosted_stream(model), "[DONE]")))
    else:
        route.respond(200, json=hosted_completion(model))

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{model}",
            "messages": [
                {"role": "developer", "content": "Be brief."},
                {"role": "user", "content": "Hi"},
            ],
            "reasoning_effort": "low",
            "stream": stream,
            **({"stream_options": {"include_usage": True}} if stream else {}),
        },
    )
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == model
    assert sent["messages"][0]["role"] == ("system" if model == MODEL else "developer")
    assert sent["reasoning_effort"] == "low"
    if stream:
        events = parse_events(response.text)
        assert events[-1] == "[DONE]"
        assert events[0]["model"] == f"nvidia/{model}"
        assert events[0]["choices"][0]["delta"]["reasoning_content"] == "Analysis"
        assert sent["stream_options"] == {"include_usage": True}
    else:
        assert response.json()["model"] == f"nvidia/{model}"
        assert response.json()["choices"][0]["message"]["reasoning_content"] == "Analysis"
    record = hosted_gateway.records[0]
    assert record.model == model
    assert (
        record.prompt_tokens,
        record.completion_tokens,
        record.cached_tokens,
        record.reasoning_tokens,
    ) == (20, 10, 8, 3)
    assert record.cost_status == "unpriced"
    assert record.cost_usd is None


async def test_tool_loop_returns_complete_typed_assistant_history(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=hosted_completion(MODEL))

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{MODEL}",
            "messages": [HISTORY, {"role": "tool", "tool_call_id": "call_1", "content": "result"}],
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][0] == {
        key: value for key, value in HISTORY.items() if key != "annotations"
    }


@pytest.mark.parametrize("role", ["system", "developer", "assistant"])
async def test_non_user_content_arrays_are_rejected(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, role: str
) -> None:
    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{MODEL}",
            "messages": [{"role": role, "content": [{"type": "text", "text": "Hi"}]}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls


@pytest.mark.parametrize(
    "error",
    [
        {"error": {"message": "Invalid option"}},
        {"message": "Invalid option", "code": 422},
        {"type": "urn:problem", "status": 422, "detail": "Invalid option"},
    ],
)
async def test_provider_rejection_messages_pass_through(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, error: dict[str, object]
) -> None:
    route = upstream.post("/chat/completions").respond(422, json=error)

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{MODEL}",
            "messages": [{"role": "user", "content": "Hi"}],
            "provider_options": {"nvidia": {"new_option": True}},
        },
    )

    assert route.called
    assert json.loads(route.calls.last.request.content)["new_option"] is True
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Invalid option"


async def test_unpriced_hosted_model_is_listed(hosted_gateway: HostedGateway) -> None:
    response = await hosted_gateway.client.get("/v1/models")

    assert response.status_code == 200
    assert {entry["id"] for entry in response.json()["data"]} == {
        f"nvidia/{model}" for model in NVIDIA_MODELS
    }


async def test_history_reasoning_cannot_bypass_guardrails(
    memory_repository: MemoryKeyRepository,
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, guardrails=GuardrailPolicy(team=(("email", "block"),))
    )

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{MODEL}",
            "messages": [{**HISTORY, "reasoning_content": "ada@example.com"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "guardrail_blocked"
    assert not upstream.calls
