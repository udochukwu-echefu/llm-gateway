import json

import httpx
import pytest
import respx

from tests.fixtures import COMPLETION, chunk, parse_events, sse

pytestmark = pytest.mark.parametrize("provider_name", ["deepseek"])


async def test_json_schema_output_is_rejected(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "result"}},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert "response_format.json_schema" in response.json()["error"]["message"]
    assert not upstream.calls


async def test_reasoning_message_is_preserved(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(
        200,
        json={
            **COMPLETION,
            "choices": [{"index": 0, "message": {"reasoning_content": "analysis"}}],
        },
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/model",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert response.json()["choices"][0]["message"]["reasoning_content"] == "analysis"


async def test_token_limit_translation(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_completion_tokens": 20,
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["max_tokens"] == 20
    assert "max_completion_tokens" not in sent


async def test_conflicting_token_limits_are_rejected(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
            "max_completion_tokens": 20,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls


async def test_reasoning_delta_is_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").respond(
        200,
        content=b"".join(
            sse(
                chunk({"reasoning_content": "analysis"}),
                "[DONE]",
            )
        ),
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "deepseek/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    assert parse_events(response.text)[0]["choices"][0]["delta"]["reasoning_content"] == "analysis"
