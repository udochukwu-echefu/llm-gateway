from typing import Any

import pytest
from pydantic import ValidationError

from llm_gateway.schemas.chat import ChatCompletionRequest, Delta, ResponseMessage

USER = {"role": "user", "content": "hi"}


def chat(**fields: Any) -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate({"model": "m", "messages": [USER], **fields})


FULL_REQUEST: dict[str, Any] = {
    "model": "m",
    "messages": [
        {"role": "system", "content": "Be brief."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://x.test/a.png", "detail": "low"},
                },
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q": "cat"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "a cat"},
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        }
    ],
    "tool_choice": "auto",
    "response_format": {
        "type": "json_schema",
        "json_schema": {"name": "answer", "schema": {"type": "object"}, "strict": True},
    },
    "temperature": 0,
    "max_completion_tokens": 200,
    "stop": ["\n\n"],
}


def test_full_request_round_trips_unchanged() -> None:
    request = ChatCompletionRequest.model_validate(FULL_REQUEST)

    assert request.to_upstream("groq") == FULL_REQUEST


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"temprature": 0.2}, "Extra inputs"),
        ({"temperature": "0.2"}, "valid number"),
        ({"temperature": 3}, "less than or equal to 2"),
        ({"messages": [{"role": "robot", "content": "x"}]}, "tag"),
        ({"messages": [{"role": "user", "content": [{"type": "video"}]}]}, "tag"),
        ({"messages": [{"role": "user", "content": "x", "colour": "red"}]}, "Extra inputs"),
        ({"messages": [{"role": "assistant"}]}, "content or tool_calls"),
        ({"messages": [{"role": "tool", "content": "x"}]}, "tool_call_id"),
        ({"stream_options": {"include_usage": True}}, "only allowed when stream"),
        ({"top_logprobs": 3}, "requires logprobs"),
        ({"tool_choice": "required"}, "requires tools"),
        ({"stop": ["a", "b", "c", "d", "e"]}, "at most 4"),
        ({"tools": [{"type": "function", "function": {"name": "has space"}}]}, "pattern"),
        ({"provider_options": {"groqq": {}}}, "groqq"),
        ({"provider_options": {"groq": {"messages": []}}}, "cannot set standard fields"),
    ],
)
def test_invalid_requests_are_rejected(fields: dict[str, Any], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        chat(**fields)


def test_assistant_history_may_carry_output_only_fields() -> None:
    # What an OpenAI SDK sends when you append the previous response message as-is.
    echoed: dict[str, Any] = {
        "role": "assistant",
        "content": "hello",
        "refusal": None,
        "annotations": [],
        "reasoning_content": "The user greeted me...",
    }

    request = chat(messages=[USER, echoed])

    assert request.to_upstream("deepseek")["messages"][1] == {
        "role": "assistant",
        "content": "hello",
        "refusal": None,
    }


def test_only_the_serving_providers_options_are_sent() -> None:
    request = chat(
        provider_options={
            "groq": {"reasoning_format": "parsed"},
            "deepseek": {"thinking": {"type": "enabled"}},
        }
    )

    payload = request.to_upstream("groq")

    assert payload["reasoning_format"] == "parsed"
    assert "thinking" not in payload
    assert "provider_options" not in payload


def test_streaming_always_asks_the_provider_for_usage() -> None:
    assert chat(stream=True).to_upstream("groq")["stream_options"] == {"include_usage": True}
    assert not chat(stream=True).client_wants_stream_usage
    assert chat(stream=True, stream_options={"include_usage": True}).client_wants_stream_usage


def test_non_streaming_request_has_no_stream_options() -> None:
    assert "stream_options" not in chat().to_upstream("groq")


@pytest.mark.parametrize("model", [ResponseMessage, Delta])
def test_reasoning_content_is_a_typed_optional_field(model: type[ResponseMessage | Delta]) -> None:
    assert model().reasoning_content is None
    assert model(reasoning_content="Analysis").reasoning_content == "Analysis"
    with pytest.raises(ValidationError):
        model.model_validate({"reasoning_content": ["invalid"]})
