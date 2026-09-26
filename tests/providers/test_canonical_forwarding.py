import json

import httpx
import pytest
import respx

from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from llm_gateway.schemas.embeddings import EmbeddingRequest
from tests.fixtures import (
    CANONICAL_CHAT_VALUES,
    CANONICAL_EMBEDDING_VALUES,
    COMPLETION,
    DOCUMENTED_CHAT_REJECTIONS,
    EMBEDDINGS,
    STREAM,
    sse,
)


def test_forwarding_matrix_covers_every_canonical_field() -> None:
    assert set(CANONICAL_CHAT_VALUES) == set(ChatCompletionRequest.model_fields)
    assert set(CANONICAL_EMBEDDING_VALUES) == set(EmbeddingRequest.model_fields)


@pytest.mark.parametrize(
    ("provider_name", "parameter"),
    [
        (name, parameter)
        for name, rejected in DOCUMENTED_CHAT_REJECTIONS.items()
        for parameter in CANONICAL_CHAT_VALUES
        if parameter not in rejected
    ],
)
async def test_canonical_chat_parameter_is_forwarded(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    parameter: str,
) -> None:
    body = {
        "messages": CANONICAL_CHAT_VALUES["messages"],
        parameter: CANONICAL_CHAT_VALUES[parameter],
        "model": f"{provider_name}/model",
    }
    if parameter == "stream_options":
        body["stream"] = True
    if parameter == "top_logprobs":
        body["logprobs"] = True
    if parameter == "tool_choice":
        body["tools"] = CANONICAL_CHAT_VALUES["tools"]
    wire = (
        httpx.Response(200, content=b"".join(sse(*STREAM, "[DONE]")))
        if body.get("stream")
        else httpx.Response(200, json=COMPLETION)
    )
    route = upstream.post("/chat/completions").mock(return_value=wire)

    response = await client.post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    if parameter == "provider_options":
        assert sent["extension"] == provider_name
        assert "provider_options" not in sent
    elif parameter == "max_completion_tokens" and provider_name == "deepseek":
        assert sent["max_tokens"] == CANONICAL_CHAT_VALUES[parameter]
        assert parameter not in sent
    else:
        assert sent[parameter] == CANONICAL_CHAT_VALUES[parameter]


@pytest.mark.parametrize("provider_name", ["gemini", "openai"])
@pytest.mark.parametrize("parameter", CANONICAL_EMBEDDING_VALUES)
async def test_canonical_embedding_parameter_is_forwarded(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    parameter: str,
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)
    body = {
        "input": "hello",
        parameter: CANONICAL_EMBEDDING_VALUES[parameter],
        "model": f"{provider_name}/embedding",
    }

    response = await client.post("/v1/embeddings", json=body)

    assert response.status_code == 200
    sent = json.loads(route.calls.last.request.content)
    if parameter == "provider_options":
        assert sent["extension"] == provider_name
        assert "provider_options" not in sent
    else:
        assert sent[parameter] == CANONICAL_EMBEDDING_VALUES[parameter]
