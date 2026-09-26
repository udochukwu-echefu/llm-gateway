"""Canonical streamed responses as seen over HTTP."""

import json
from typing import Any

import httpx
import pytest
import respx

from tests.fixtures import (
    CHAT_REQUEST,
    STREAM,
    USAGE_CHUNK,
    chunk,
    parse_events,
    prefixed,
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


async def test_usage_attached_to_a_content_chunk_is_removed_not_the_chunk(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    last_with_usage = {**STREAM[1], "usage": USAGE_CHUNK["usage"]}
    upstream.post("/chat/completions").mock(
        return_value=stream_reply(STREAM[0], last_with_usage, "[DONE]")
    )

    events = await stream(client, STREAM_REQUEST)

    assert events == [*(prefixed(c) for c in STREAM), "[DONE]"]


async def test_finished_stream_without_done_marker_gets_one(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=stream_reply(*STREAM))

    events = await stream(client, STREAM_REQUEST)

    assert events == [*(prefixed(c) for c in STREAM), "[DONE]"]


async def test_stream_cut_off_before_finishing_ends_with_an_error(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=stream_reply(STREAM[0]))

    events = await stream(client, STREAM_REQUEST)

    assert events[0] == prefixed(STREAM[0])
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

    assert events[0] == prefixed(STREAM[0])
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

    assert events == [*(prefixed(c) for c in tool_stream), "[DONE]"]
