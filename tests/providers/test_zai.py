import asyncio
import json
from dataclasses import replace
from decimal import Decimal

import pytest
import respx

from llm_gateway.routing.policy import ModelPolicy
from tests.conftest import MemoryKeyRepository
from tests.fixtures import parse_events, sse
from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import HISTORY, hosted_completion, hosted_stream

pytestmark = pytest.mark.parametrize("provider_name", ["zai"])
MODEL = "glm-5.3-flash"


@pytest.mark.parametrize("stream", [False, True])
async def test_chat_preserves_reasoning_cache_usage_and_prices_receipt(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, stream: bool
) -> None:
    route = upstream.post("/chat/completions")
    if stream:
        route.respond(200, content=b"".join(sse(*hosted_stream(MODEL), "[DONE]")))
    else:
        route.respond(200, json=hosted_completion(MODEL))

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"zai/{MODEL}",
            "messages": [
                {"role": "developer", "content": "Be brief."},
                {"role": "user", "content": "Hi"},
            ],
            "max_completion_tokens": 32,
            "stream": stream,
            **({"stream_options": {"include_usage": True}} if stream else {}),
        },
    )
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == MODEL
    assert sent["messages"][0]["role"] == "system"
    assert sent["max_completion_tokens"] == 32
    if stream:
        events = parse_events(response.text)
        assert events[-1] == "[DONE]"
        assert events[0]["choices"][0]["delta"]["reasoning_content"] == "Analysis"
        assert events[-2]["usage"]["prompt_tokens_details"]["cached_tokens"] == 8
        assert sent["stream_options"] == {"include_usage": True}
    else:
        assert response.json()["choices"][0]["message"]["reasoning_content"] == "Analysis"
    record = hosted_gateway.records[0]
    assert (
        record.prompt_tokens,
        record.completion_tokens,
        record.cached_tokens,
        record.reasoning_tokens,
    ) == (20, 10, 8, 3)
    assert record.cost_status == "priced"
    assert record.cost_usd == Decimal("0.00000704")


async def test_preserved_thinking_history_is_sent(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=hosted_completion(MODEL))

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"zai/{MODEL}",
            "messages": [HISTORY, {"role": "tool", "tool_call_id": "call_1", "content": "result"}],
            "provider_options": {"zai": {"thinking": {"clear_thinking": False}}},
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][0]["reasoning_content"] == HISTORY["reasoning_content"]
    assert sent["thinking"] == {"clear_thinking": False}
    assert "annotations" not in sent["messages"][0]


@pytest.mark.parametrize(
    ("fields", "parameter"),
    [
        (
            {"response_format": {"type": "json_schema", "json_schema": {"name": "result"}}},
            "response_format.json_schema",
        ),
        (
            {"provider_options": {"zai": {"thinking": {"type": "disabled"}}}},
            "thinking.type=disabled",
        ),
    ],
)
async def test_documented_restrictions_fail_before_network(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    fields: dict[str, object],
    parameter: str,
) -> None:
    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={"model": f"zai/{MODEL}", "messages": [{"role": "user", "content": "Hi"}], **fields},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert parameter in response.json()["error"]["message"]
    assert not upstream.calls


@pytest.mark.parametrize("allowed", ["sg", "eu"])
async def test_singapore_residency_is_applied_before_network(
    memory_repository: MemoryKeyRepository,
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    allowed: str,
) -> None:
    record = next(iter(memory_repository.records.values()))
    regions = ("sg",) if allowed == "sg" else ("eu",)
    memory_repository.records[record.key_id] = replace(
        record, policy=ModelPolicy(team_regions=regions)
    )
    route = upstream.post("/chat/completions").respond(200, json=hosted_completion(MODEL))

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={"model": f"zai/{MODEL}", "messages": [{"role": "user", "content": "Hi"}]},
    )
    listing = await hosted_gateway.client.get("/v1/models")

    if allowed == "sg":
        assert response.status_code == 200
        assert route.called
        assert {entry["id"] for entry in listing.json()["data"]} == {
            "zai/glm-5.3-flash",
            "zai/glm-5.3-flashx",
            "zai/glm-5.3",
        }
    else:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "model_not_allowed"
        assert "region 'sg' is not permitted" in response.json()["error"]["message"]
        assert not route.called
        assert listing.json()["data"] == []
