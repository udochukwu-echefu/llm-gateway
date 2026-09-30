"""Wire samples shared by provider contracts and HTTP tests."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

# Independent expectations: never derive regression cases from production capabilities.
DOCUMENTED_CHAT_REJECTIONS = {
    "groq": frozenset(
        {"logprobs", "top_logprobs", "logit_bias", "frequency_penalty", "presence_penalty"}
    ),
    "deepseek": frozenset({"frequency_penalty", "presence_penalty"}),
    "gemini": frozenset[str](),
    "openai": frozenset[str](),
    "zai": frozenset[str](),
    "nvidia": frozenset({"top_p", "presence_penalty", "frequency_penalty", "n"}),
}
CANONICAL_CHAT_VALUES: dict[str, Any] = {
    "model": "model",
    "messages": [{"role": "user", "content": "Hi"}],
    "stream": True,
    "stream_options": {"include_usage": True},
    "temperature": 0.2,
    "top_p": 0.5,
    "max_tokens": 10,
    "max_completion_tokens": 10,
    "n": 1,
    "stop": "END",
    "seed": 42,
    "presence_penalty": 0.1,
    "frequency_penalty": 0.1,
    "logprobs": True,
    "top_logprobs": 1,
    "logit_bias": {"1": 1},
    "tools": [{"type": "function", "function": {"name": "lookup"}}],
    "tool_choice": "auto",
    "parallel_tool_calls": True,
    "response_format": {"type": "json_object"},
    "reasoning_effort": "low",
    "service_tier": "auto",
    "user": "opaque-user",
    "safety_identifier": "opaque-user",
    "provider_options": {name: {"extension": name} for name in DOCUMENTED_CHAT_REJECTIONS},
}
CANONICAL_EMBEDDING_VALUES: dict[str, Any] = {
    "model": "embedding",
    "input": [[1, 2]],
    "encoding_format": "base64",
    "dimensions": 2,
    "user": "opaque-user",
    "provider_options": {name: {"extension": name} for name in ("gemini", "openai")},
}

# Captured Gemini response shape: zero index omitted, index 1 present, usage absent.
GEMINI_ZERO_OMITTING_EMBEDDINGS = {
    "object": "list",
    "model": "gemini-embedding-001",
    "data": [
        {"embedding": [0.1, -0.2], "object": "embedding"},
        {"embedding": [0.3, 0.4], "object": "embedding", "index": 1},
    ],
}
GEMINI_ZERO_OMITTING_TOOL_CHUNK = {
    "id": "chatcmpl-1",
    "model": "gemini-model",
    "object": "chat.completion.chunk",
    "choices": [
        {
            "delta": {
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ]
            },
            "finish_reason": "tool_calls",
        }
    ],
}

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
