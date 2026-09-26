"""The canonical format as seen over HTTP: validation, normalisation and usage accounting."""

import json
from typing import Any

import httpx
import pytest
import respx
import structlog
from structlog.testing import capture_logs

from tests.test_chat_completions import (
    CHAT_REQUEST,
    COMPLETION,
    STREAM,
    USAGE_CHUNK,
    chunk,
    parse_events,
    sse,
)

STREAM_REQUEST = {**CHAT_REQUEST, "stream": True}


def stream_reply(*events: dict[str, Any] | str) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=b"".join(sse(*events))
    )


async def stream(client: httpx.AsyncClient, body: dict[str, Any]) -> list[Any]:
    async with client.stream("POST", "/v1/chat/completions", json=body) as response:
        assert response.status_code == 200
        return parse_events((await response.aread()).decode())


async def test_unknown_field_error_points_to_provider_options(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/chat/completions", json={**CHAT_REQUEST, "top_k": 5})

    assert response.status_code == 400
    assert response.json()["error"]["message"] == (
        "Invalid request body. top_k: unknown field. "
        "Provider-specific fields go in provider_options.<provider>."
    )


async def test_provider_options_reach_the_configured_provider(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    await client.post(
        "/v1/chat/completions",
        json={
            **CHAT_REQUEST,
            "provider_options": {"groq": {"top_k": 5}, "gemini": {"safety": "strict"}},
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["top_k"] == 5  # the test settings serve requests with Groq
    assert "safety" not in sent


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


async def test_stream_requests_usage_but_hides_it_from_clients_that_did_not_ask(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").mock(
        return_value=stream_reply(*STREAM, USAGE_CHUNK, "[DONE]")
    )

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        events = await stream(client, STREAM_REQUEST)

    assert json.loads(route.calls.last.request.content)["stream_options"] == {"include_usage": True}
    assert events == [*STREAM, "[DONE]"]
    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["total_tokens"] == 11  # recorded even though the client never saw it


async def test_stream_passes_usage_to_clients_that_asked(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(
        return_value=stream_reply(*STREAM, USAGE_CHUNK, "[DONE]")
    )

    events = await stream(client, {**STREAM_REQUEST, "stream_options": {"include_usage": True}})

    assert events == [*STREAM, USAGE_CHUNK, "[DONE]"]


async def test_usage_attached_to_a_content_chunk_is_removed_not_the_chunk(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    last_with_usage = {**STREAM[1], "usage": USAGE_CHUNK["usage"]}
    upstream.post("/chat/completions").mock(
        return_value=stream_reply(STREAM[0], last_with_usage, "[DONE]")
    )

    events = await stream(client, STREAM_REQUEST)

    assert events == [*STREAM, "[DONE]"]


async def test_finished_stream_without_done_marker_gets_one(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=stream_reply(*STREAM))

    events = await stream(client, STREAM_REQUEST)

    assert events == [*STREAM, "[DONE]"]


async def test_stream_cut_off_before_finishing_ends_with_an_error(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=stream_reply(STREAM[0]))

    events = await stream(client, STREAM_REQUEST)

    assert events[0] == STREAM[0]
    assert events[-1]["error"]["code"] == "upstream_stream_truncated"


BAD_EVENTS: list[tuple[Any, str]] = [
    ("{not json", "upstream_invalid_response"),
    ({"id": "x", "model": "m", "choices": [{"delta": {}}]}, "upstream_invalid_response"),
    ({"error": {"message": "overloaded", "type": "server_error"}}, "upstream_stream_error"),
]


@pytest.mark.parametrize(("bad_event", "code"), BAD_EVENTS)
async def test_bad_event_mid_stream_ends_with_an_error(
    client: httpx.AsyncClient, upstream: respx.MockRouter, bad_event: Any, code: str
) -> None:
    upstream.post("/chat/completions").mock(
        return_value=stream_reply(STREAM[0], bad_event, STREAM[1], "[DONE]")
    )

    events = await stream(client, STREAM_REQUEST)

    assert events[0] == STREAM[0]
    assert events[1]["error"]["code"] == code
    assert len(events) == 2  # nothing after the error
    assert "overloaded" not in json.dumps(events)


async def test_tool_call_deltas_stream_through(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    tool_stream = [
        chunk(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": ""},
                    }
                ],
            }
        ),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"q":"cat"}'}}]}),
        chunk({}, finish_reason="tool_calls"),
    ]
    upstream.post("/chat/completions").mock(return_value=stream_reply(*tool_stream, "[DONE]"))

    events = await stream(client, STREAM_REQUEST)

    assert events == [*tool_stream, "[DONE]"]


EMBEDDINGS = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, -0.2]}],
    "model": "text-embedding-004",
    "usage": {"prompt_tokens": 3, "total_tokens": 3},
}


async def test_embeddings_are_forwarded_and_validated(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "text-embedding-004", "input": ["hello"]}

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post("/v1/embeddings", json=body)

    assert response.status_code == 200
    assert response.json() == EMBEDDINGS
    assert json.loads(route.calls.last.request.content) == body
    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["prompt_tokens"] == 3


async def test_invalid_embedding_request_is_rejected(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/embeddings")

    response = await client.post("/v1/embeddings", json={"model": "e", "input": []})

    assert response.status_code == 400
    assert not route.called
