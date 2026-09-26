import json

import httpx
import pytest
import respx

from tests.fixtures import COMPLETION, EMBEDDINGS

pytestmark = pytest.mark.parametrize("provider_name", ["openai"])


async def test_native_completion_limit_is_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "openai/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_completion_tokens": 10,
        },
    )

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    assert sent["max_completion_tokens"] == 10
    assert "max_tokens" not in sent


async def test_embedding_parameters_are_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {"input": [[1, 2]], "dimensions": 2, "encoding_format": "float", "user": "u"}

    response = await client.post("/v1/embeddings", json={"model": "openai/embedding", **body})

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content) == {"model": "embedding", **body}
