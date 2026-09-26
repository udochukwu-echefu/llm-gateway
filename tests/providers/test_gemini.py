import json

import httpx
import pytest
import respx

from tests.fixtures import (
    COMPLETION,
    EMBEDDINGS,
    GEMINI_ZERO_OMITTING_EMBEDDINGS,
    GEMINI_ZERO_OMITTING_TOOL_CHUNK,
    parse_events,
    sse,
)

pytestmark = pytest.mark.parametrize("provider_name", ["gemini"])


async def test_captured_embedding_shape_restores_index_without_inventing_usage(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/embeddings").respond(200, json=GEMINI_ZERO_OMITTING_EMBEDDINGS)

    response = await client.post(
        "/v1/embeddings",
        json={
            "model": "gemini/gemini-embedding-001",
            "input": ["one", "two"],
        },
    )

    assert response.status_code == 200
    assert [item["index"] for item in response.json()["data"]] == [0, 1]
    assert "usage" not in response.json()


async def test_streaming_tool_call_omitted_zero_indices_are_returned(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").respond(
        200,
        content=b"".join(sse(GEMINI_ZERO_OMITTING_TOOL_CHUNK, "[DONE]")),
    )

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gemini/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    events = parse_events(response.text)
    assert response.status_code == 200
    assert events[-1] == "[DONE]"
    choice = events[0]["choices"][0]
    assert choice["index"] == 0
    assert choice["delta"]["tool_calls"][0]["index"] == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"input": [1, 2]},
        {"input": [[1, 2]]},
        {"dimensions": 64},
        {"encoding_format": "base64"},
        {"user": "u"},
    ],
)
async def test_undocumented_embedding_options_are_forwarded(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    response = await client.post(
        "/v1/embeddings",
        json={
            "model": "gemini/embedding",
            "input": "hello",
            **extra,
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert all(sent[key] == value for key, value in extra.items())


@pytest.mark.parametrize(
    "extra",
    [
        {"max_tokens": 10},
        {"max_completion_tokens": 10},
        {"n": 2},
        {"temperature": 0.2},
        {"top_p": 0.5},
        {"stop": "END"},
    ],
    ids=["max_tokens", "max_completion_tokens", "n", "temperature", "top_p", "stop"],
)
async def test_undocumented_limits_are_forwarded(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gemini/model",
            "messages": [{"role": "user", "content": "Hi"}],
            **extra,
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert all(sent[key] == value for key, value in extra.items())
