"""Synthetic OpenAI wire responses with known usage; no input text is retained."""

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable

from loadtest.fake_provider.configuration import FakeSettings

type Sleep = Callable[[float], Awaitable[None]]
USAGE = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


def completion(model: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Synthetic answer."},
                "finish_reason": "stop",
            }
        ],
        "usage": USAGE,
    }


def embeddings(model: str, count: int, dimensions: int) -> dict[str, object]:
    return {
        "object": "list",
        "model": model,
        "data": [
            {"object": "embedding", "index": index, "embedding": [0.125] * dimensions}
            for index in range(count)
        ],
        "usage": {"prompt_tokens": 10 * count, "total_tokens": 10 * count},
    }


async def stream(
    model: str, settings: FakeSettings, include_usage: bool, sleep: Sleep = asyncio.sleep
) -> AsyncGenerator[bytes]:
    for index in range(settings.chunk_count):
        if index:
            await sleep(settings.chunk_interval_ms / 1000)
        yield _event(model, [{"index": 0, "delta": {"content": "word "}, "finish_reason": None}])
    await sleep(settings.chunk_interval_ms / 1000)
    yield _event(model, [{"index": 0, "delta": {}, "finish_reason": "stop"}])
    if include_usage:
        yield _event(model, [], USAGE)
    yield b"data: [DONE]\n\n"


def _event(
    model: str, choices: list[dict[str, object]], usage: dict[str, int] | None = None
) -> bytes:
    payload: dict[str, object] = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": choices,
    }
    if usage is not None:
        payload["usage"] = usage
    return f"data: {json.dumps(payload)}\n\n".encode()
