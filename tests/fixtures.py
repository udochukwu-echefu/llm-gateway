"""Wire samples shared by provider contracts and HTTP tests."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

CHAT_REQUEST: dict[str, Any] = {
    "model": "groq/llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": "Say hi"}],
    "temperature": 0.2,
}
COMPLETION: dict[str, Any] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "created": 1790000000,
    "model": "llama-3.3-70b-versatile",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
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
STREAM = [
    chunk({"role": "assistant", "content": "h"}),
    chunk({"content": "i"}, finish_reason="stop"),
]
EMBEDDINGS = {
    "object": "list",
    "data": [{"object": "embedding", "index": 0, "embedding": [0.1, -0.2]}],
    "model": "text-embedding-004",
    "usage": {"prompt_tokens": 3, "total_tokens": 3},
}


def prefixed(data: dict[str, Any], provider: str = "groq") -> dict[str, Any]:
    return {**data, "model": f"{provider}/{data['model']}"}


def sse(*events: dict[str, Any] | str) -> list[bytes]:
    return [
        f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n".encode()
        for event in events
    ]


SSE_CHUNKS = sse(*STREAM, "[DONE]")


def parse_events(body: str) -> list[Any]:
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
