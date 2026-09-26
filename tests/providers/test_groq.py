import json

import httpx
import pytest
import respx

from tests.fixtures import COMPLETION, chunk, parse_events, sse

pytestmark = pytest.mark.parametrize("provider_name", ["groq"])


async def test_supported_token_limit_and_single_choice_are_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_completion_tokens": 10,
            "n": 1,
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["max_completion_tokens"] == 10
    assert sent["n"] == 1
    assert "max_tokens" not in sent


async def test_canonical_reasoning_takes_precedence_and_raw_tags_are_kept(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").respond(
        200,
        json={
            **COMPLETION,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "content": "<think>quoted</think>",
                        "reasoning": "provider",
                        "reasoning_content": "canonical",
                    },
                }
            ],
        },
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    message = response.json()["choices"][0]["message"]
    assert message["reasoning_content"] == "canonical"
    assert message["content"] == "<think>quoted</think>"
    assert "reasoning" not in message


@pytest.mark.parametrize("stream", [False, True])
async def test_reasoning_is_normalized(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    stream: bool,
) -> None:
    message = {"content": "answer", "reasoning": "analysis"}
    response = (
        httpx.Response(200, content=b"".join(sse(chunk(message), "[DONE]")))
        if stream
        else httpx.Response(200, json={**COMPLETION, "choices": [{"index": 0, "message": message}]})
    )
    upstream.post("/chat/completions").mock(return_value=response)

    result = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": stream,
        },
    )

    body = parse_events(result.text)[0] if stream else result.json()
    output = body["choices"][0]["delta" if stream else "message"]
    assert output["reasoning_content"] == "analysis"
    assert "reasoning" not in output


@pytest.mark.parametrize(
    "extra", [{"n": 2}, {"messages": [{"role": "user", "content": "Hi", "name": "u"}]}]
)
async def test_restricted_values_rejected(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
            **extra,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls
