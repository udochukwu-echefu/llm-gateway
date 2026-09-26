import httpx
import respx
import structlog
from structlog.testing import capture_logs

from tests.fixtures import CHAT_REQUEST, COMPLETION


async def test_unknown_field_error_points_to_provider_options(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/chat/completions", json={**CHAT_REQUEST, "top_k": 5})

    assert response.status_code == 400
    assert response.json()["error"]["message"] == (
        "Invalid request body. top_k: unknown field. "
        "Provider-specific fields go in provider_options.<provider>."
    )


async def test_provider_extras_in_responses_are_kept(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(200, json={**COMPLETION, "x_groq": {"id": "req_1"}})

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.json()["x_groq"] == {"id": "req_1"}


async def test_malformed_provider_response_is_a_502(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(200, json={"id": "x", "choices": "nope"})

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_invalid_response"


async def test_usage_is_recorded_in_the_access_log(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(200, json=COMPLETION)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    access = next(entry for entry in logs if entry["event"] == "request")
    assert (access["prompt_tokens"], access["completion_tokens"], access["total_tokens"]) == (
        9,
        1,
        10,
    )
