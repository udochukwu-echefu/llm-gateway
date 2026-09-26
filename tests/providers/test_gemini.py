import json

import httpx
import pytest
import respx

from tests.fixtures import COMPLETION, EMBEDDINGS

pytestmark = pytest.mark.parametrize("provider_name", ["gemini"])


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


@pytest.mark.parametrize("extra", [{"max_tokens": 10}, {"max_completion_tokens": 10}, {"n": 2}])
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
