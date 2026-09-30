"""Synthetic OpenAI-shaped provider data, not captured live measurements."""

from typing import Any

from tests.fixtures import COMPLETION, chunk

HOSTED_MODELS = {"zai": "glm-5.3-flash", "nvidia": "moonshotai/kimi-k3"}
HOSTED_USAGE = {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30,
    "prompt_tokens_details": {"cached_tokens": 8},
    "completion_tokens_details": {"reasoning_tokens": 3},
}
HISTORY = {
    "role": "assistant",
    "content": None,
    "reasoning_content": "Use the lookup tool.",
    "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}
    ],
    "annotations": [],
}


def hosted_completion(model: str) -> dict[str, Any]:
    return {
        **COMPLETION,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "OK", "reasoning_content": "Analysis"},
                "finish_reason": "stop",
            }
        ],
        "usage": HOSTED_USAGE,
    }


def hosted_stream(model: str) -> list[dict[str, Any]]:
    return [
        {**chunk({"reasoning_content": "Analysis"}), "model": model},
        {**chunk({"content": "OK"}, "stop"), "model": model, "usage": HOSTED_USAGE},
    ]
