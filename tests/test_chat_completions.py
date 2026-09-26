import json
from collections.abc import AsyncIterator
from typing import Any

import anyio
import httpx
import pytest
import respx
from fastapi import FastAPI
from starlette.types import Message

from tests.conftest import UPSTREAM_KEY

CHAT_REQUEST: dict[str, Any] = {
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": "Say hi"}],
    "temperature": 0.2,
}
COMPLETION: dict[str, Any] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1790000000,
    "model": "llama-3.3-70b-versatile",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "hi"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10},
}


def chunk(delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 1790000000,
        "model": "llama-3.3-70b-versatile",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


USAGE_CHUNK: dict[str, Any] = {
    **chunk({}),
    "choices": [],
    "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11},
}
STREAM: list[dict[str, Any]] = [
    chunk({"role": "assistant", "content": "h"}),
    chunk({"content": "i"}, finish_reason="stop"),
]


def sse(*events: dict[str, Any] | str) -> list[bytes]:
    return [
        f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n".encode()
        for event in events
    ]


SSE_CHUNKS = sse(*STREAM, "[DONE]")


def parse_events(body: str) -> list[Any]:
    """The data of every SSE event, JSON-decoded ([DONE] stays a string)."""
    events: list[Any] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            data = line.removeprefix("data: ")
            events.append(data if data == "[DONE]" else json.loads(data))
    return events


def sse_response(chunks: list[bytes]) -> httpx.Response:
    async def stream() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream())


async def test_non_streaming_request_is_forwarded_as_sent(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    route = upstream.post("/chat/completions").respond(
        200, json=COMPLETION, headers={"x-request-id": "req_upstream_1"}
    )
    body = json.dumps(CHAT_REQUEST).encode()

    response = await client.post(
        "/v1/chat/completions",
        content=body,
        headers={"content-type": "application/json", "authorization": "Bearer client-key"},
    )

    assert response.status_code == 200
    assert response.json() == COMPLETION
    sent = route.calls.last.request
    # Exactly what the client set: no defaults added, nothing dropped.
    assert json.loads(sent.content) == CHAT_REQUEST
    # The provider sees our key, never the client's.
    assert sent.headers["authorization"] == f"Bearer {UPSTREAM_KEY}"


async def test_streaming_request_relays_every_chunk(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").mock(return_value=sse_response(SSE_CHUNKS))

    async with client.stream(
        "POST", "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    ) as response:
        received = (await response.aread()).decode()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert parse_events(received) == [*STREAM, "[DONE]"]


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (b"not json", "body"),
        (b"[]", "body"),
        (json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode(), "model"),
        (json.dumps({"model": "m", "messages": []}).encode(), "messages"),
        (json.dumps({**CHAT_REQUEST, "stream": "yes"}).encode(), "stream"),
    ],
)
async def test_invalid_body_is_rejected_before_reaching_the_provider(
    client: httpx.AsyncClient, upstream: respx.MockRouter, body: bytes, fragment: str
) -> None:
    route = upstream.post("/chat/completions")

    response = await client.post(
        "/v1/chat/completions", content=body, headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "invalid_body"
    assert fragment in error["message"]
    assert not route.called


async def test_non_json_content_type_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/chat/completions", content=b"model=x", headers={"content-type": "text/plain"}
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_oversized_body_is_rejected(client: httpx.AsyncClient) -> None:
    oversized = {**CHAT_REQUEST, "messages": [{"role": "user", "content": "x" * 5000}]}

    response = await client.post("/v1/chat/completions", json=oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


async def test_oversized_chunked_body_is_rejected(client: httpx.AsyncClient) -> None:
    async def chunked() -> AsyncIterator[bytes]:  # no Content-Length header is sent
        for _ in range(10):
            yield b"x" * 1000

    response = await client.post(
        "/v1/chat/completions", content=chunked(), headers={"content-type": "application/json"}
    )

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("upstream_status", "expected_status", "expected_code"),
    [
        (400, 400, "upstream_rejected_request"),
        (404, 404, "upstream_rejected_request"),
        (401, 502, "upstream_auth_failed"),
        (403, 502, "upstream_auth_failed"),
        (408, 504, "upstream_timeout"),
        (429, 429, "upstream_rate_limited"),
        (500, 502, "upstream_server_error"),
        (503, 502, "upstream_server_error"),
    ],
)
async def test_upstream_error_statuses_are_mapped(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    upstream_status: int,
    expected_status: int,
    expected_code: str,
) -> None:
    upstream.post("/chat/completions").respond(
        upstream_status, json={"error": {"message": "provider says no"}}
    )

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


async def test_client_errors_pass_the_provider_message_through(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(
        404, json={"error": {"message": "The model `nope` does not exist"}}
    )

    response = await client.post("/v1/chat/completions", json={**CHAT_REQUEST, "model": "nope"})

    assert response.json()["error"]["message"] == "The model `nope` does not exist"


async def test_provider_auth_failure_does_not_leak_provider_details(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(
        401, json={"error": {"message": "Invalid API Key sk-upstream-..."}}
    )

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert "sk-upstream" not in response.text
    assert "Invalid API Key" not in response.text


async def test_rate_limit_forwards_retry_after(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(429, headers={"retry-after": "7"}, json={})

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"


@pytest.mark.parametrize(
    ("exception", "expected_status", "expected_code"),
    [
        (httpx.ConnectError("refused"), 502, "upstream_unavailable"),
        (httpx.ConnectTimeout("slow"), 504, "upstream_timeout"),
        (httpx.ReadTimeout("slow"), 504, "upstream_timeout"),
        (httpx.PoolTimeout("busy"), 503, "gateway_overloaded"),
    ],
)
async def test_transport_failures_are_mapped(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    exception: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    upstream.post("/chat/completions").mock(side_effect=exception)

    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


async def test_stream_interrupted_mid_way_ends_with_an_error_event(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    async def breaks_after_first_chunk() -> AsyncIterator[bytes]:
        yield SSE_CHUNKS[0]
        raise httpx.ReadTimeout("provider stalled")

    upstream.post("/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=breaks_after_first_chunk()
        )
    )

    async with client.stream(
        "POST", "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    ) as response:
        events = [line async for line in response.aiter_lines() if line.startswith("data: ")]

    assert response.status_code == 200
    assert len(events) == 2
    error = json.loads(events[-1].removeprefix("data: "))["error"]  # after the first chunk
    assert error["code"] == "upstream_timeout"


async def test_client_disconnect_mid_stream_releases_the_upstream_connection(
    app: FastAPI, upstream: respx.MockRouter
) -> None:
    class StalledStream(httpx.AsyncByteStream):
        """Sends one chunk, then stalls like a slow model would."""

        closed = False

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield SSE_CHUNKS[0]
            await anyio.sleep_forever()

        async def aclose(self) -> None:
            self.closed = True

    stalled = StalledStream()
    upstream.post("/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stalled
        )
    )

    # Drive the ASGI app directly so the client can disconnect after the first chunk.
    body = json.dumps({**CHAT_REQUEST, "stream": True}).encode()
    first_chunk_sent = anyio.Event()
    request_delivered = False

    async def receive() -> Message:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await first_chunk_sent.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            first_chunk_sent.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},  # what uvicorn reports
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 50000),
        "server": ("gateway.test", 80),
    }

    async with app.router.lifespan_context(app):
        with anyio.fail_after(5):
            await app(scope, receive, send)

    assert stalled.closed
