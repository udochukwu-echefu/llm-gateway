import json

import httpx
import respx
import structlog
from structlog.testing import capture_logs

from tests.fixtures import EMBEDDINGS, prefixed


async def test_embeddings_are_forwarded_and_validated(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/text-embedding-004", "input": ["hello"]}

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post("/v1/embeddings", json=body)

    assert response.status_code == 200
    assert response.json() == prefixed(EMBEDDINGS, "openai")
    assert json.loads(route.calls.last.request.content) == {**body, "model": "text-embedding-004"}
    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["prompt_tokens"] == 3


async def test_invalid_embedding_request_is_rejected(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/embeddings")

    response = await client.post("/v1/embeddings", json={"model": "e", "input": []})

    assert response.status_code == 400
    assert not route.called
