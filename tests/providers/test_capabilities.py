import json
from dataclasses import replace

import httpx
import pytest
import respx

from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import Capabilities
from llm_gateway.providers.openai import OpenAIAdapter
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.fixtures import COMPLETION, STREAM, sse


@pytest.mark.parametrize("provider_name", ["openai"])
@pytest.mark.parametrize(
    ("capabilities", "endpoint", "fields", "parameter"),
    [
        pytest.param(
            replace(OpenAIAdapter.capabilities, supports_stream_usage=False),
            "chat/completions",
            {
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            "stream_options.include_usage",
            id="stream_usage",
        ),
        pytest.param(
            replace(OpenAIAdapter.capabilities, supports_token_inputs=False),
            "embeddings",
            {"input": [1, 2]},
            "input (token IDs)",
            id="token_inputs",
        ),
        pytest.param(
            replace(
                OpenAIAdapter.capabilities,
                unsupported_embedding_parameters=frozenset({"dimensions"}),
            ),
            "embeddings",
            {"input": "Hi", "dimensions": 2},
            "dimensions",
            id="embedding_parameter",
        ),
    ],
)
async def test_optional_capability_rejection_is_an_http_400(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    capabilities: Capabilities,
    endpoint: str,
    fields: dict[str, object],
    parameter: str,
) -> None:
    # These restrictions are not enabled on today's four adapters, but their shared
    # branches must still reject individually without making an HTTP call.
    monkeypatch.setattr(OpenAIAdapter, "capabilities", capabilities)
    upstream.post(f"/{endpoint}").respond(200, json={})

    model = "openai/embedding" if endpoint == "embeddings" else "openai/model"
    response = await client.post(f"/v1/{endpoint}", json={"model": model, **fields})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert f"'{parameter}'" in response.json()["error"]["message"]
    assert not upstream.calls


async def test_message_names_follow_explicit_capability(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    adapter: OpenAICompatibleAdapter,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi", "name": "participant"}],
        },
    )

    if adapter.capabilities.supports_message_names:
        assert response.status_code == 200
        assert json.loads(route.calls.last.request.content)["messages"][0]["name"] == "participant"
    else:
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_parameter"
        assert "messages[].name" in response.json()["error"]["message"]
        assert not route.called


@pytest.mark.parametrize("include_usage", [False, True])
async def test_provider_without_usage_support_never_receives_stream_options(
    upstream: respx.MockRouter,
    include_usage: bool,
) -> None:
    class NoUsageAdapter(OpenAIAdapter):
        capabilities = replace(OpenAIAdapter.capabilities, supports_stream_usage=False)

    request = ChatCompletionRequest.model_validate(
        {
            "model": "model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
            "stream_options": {"include_usage": include_usage},
        }
    )
    route = upstream.post("/chat/completions").respond(
        200, content=b"".join(sse(*STREAM, "[DONE]"))
    )
    async with httpx.AsyncClient(base_url="https://upstream.test/v1") as http:
        adapter = NoUsageAdapter(http)

        if include_usage:
            with pytest.raises(GatewayError) as exc:
                await adapter.open_chat_stream(request, "model")
            assert exc.value.code == "unsupported_parameter"
            assert not route.called
        else:
            stream = await adapter.open_chat_stream(request, "model")
            await stream.aclose()
            assert "stream_options" not in json.loads(route.calls.last.request.content)
