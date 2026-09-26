import httpx
import pytest

from llm_gateway.providers.deepseek import DeepSeekAdapter
from llm_gateway.providers.gemini import GeminiAdapter
from llm_gateway.providers.groq import GroqAdapter
from llm_gateway.providers.openai import OpenAIAdapter
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk


@pytest.mark.parametrize("stream", [False, True])
def test_deepseek_cache_hits_normalized_for_both_shapes(stream: bool) -> None:
    usage = {
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
        "prompt_cache_hit_tokens": 8,
        "prompt_cache_miss_tokens": 12,
    }
    if stream:
        chunk = ChatCompletionChunk.model_validate(
            {
                "id": "x",
                "model": "deepseek-flash",
                "choices": [],
                "usage": usage,
            }
        )
    else:
        chunk = ChatCompletion.model_validate(
            {
                "id": "x",
                "model": "deepseek-flash",
                "choices": [],
                "usage": usage,
            }
        )

    DeepSeekAdapter(httpx.AsyncClient()).normalize_chat(chunk)

    assert chunk.usage is not None
    assert chunk.usage.prompt_tokens_details is not None
    assert chunk.usage.prompt_tokens_details.cached_tokens == 8
    assert "prompt_cache_hit_tokens" not in (chunk.usage.model_extra or {})


@pytest.mark.parametrize("stream", [False, True])
def test_gemini_unreported_thinking_counts_towards_billed_output(stream: bool) -> None:
    usage = {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 58}
    if stream:
        result = ChatCompletionChunk.model_validate(
            {
                "id": "x",
                "model": "gemini-3.8-flash",
                "choices": [],
                "usage": usage,
            }
        )
    else:
        result = ChatCompletion.model_validate(
            {
                "id": "x",
                "model": "gemini-3.8-flash",
                "choices": [],
                "usage": usage,
            }
        )

    GeminiAdapter(httpx.AsyncClient()).normalize_chat(result)

    assert result.usage is not None
    assert result.usage.completion_tokens == 55
    assert result.usage.completion_tokens_details is None


@pytest.mark.parametrize("adapter_type", [GroqAdapter, OpenAIAdapter])
def test_openai_shaped_usage_is_preserved(
    adapter_type: type[GroqAdapter] | type[OpenAIAdapter],
) -> None:
    result = ChatCompletion.model_validate(
        {
            "id": "x",
            "model": "model",
            "choices": [],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 7,
                "total_tokens": 27,
                "prompt_tokens_details": {"cached_tokens": 5},
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        }
    )

    adapter_type(httpx.AsyncClient()).normalize_chat(result)

    assert result.usage is not None
    assert result.usage.prompt_tokens_details is not None
    assert result.usage.prompt_tokens_details.cached_tokens == 5
    assert result.usage.completion_tokens == 7
