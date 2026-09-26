import json

import httpx
import pytest
import respx
import structlog
from structlog.testing import capture_logs

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


@pytest.mark.parametrize("status", [200, 401])
async def test_provider_request_id_is_recorded_even_on_failure(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    status: int,
) -> None:
    upstream.post("/chat/completions").respond(
        status,
        json=COMPLETION,
        headers={"x-request-id": "provider-request"},
    )

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await client.post(
            "/v1/chat/completions",
            json={
                "model": "openai/model",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )

    assert (
        next(entry for entry in logs if entry["event"] == "request")["upstream_request_id"]
        == "provider-request"
    )


async def test_embedding_parameters_are_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {"input": [[1, 2]], "dimensions": 2, "encoding_format": "float", "user": "u"}

    response = await client.post("/v1/embeddings", json={"model": "openai/embedding", **body})

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content) == {"model": "embedding", **body}
