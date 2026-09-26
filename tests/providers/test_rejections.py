from dataclasses import replace
from typing import Any

import httpx
import pytest
import respx

from llm_gateway.providers.groq import GroqAdapter
from llm_gateway.schemas.common import ProviderName
from tests.fixtures import CANONICAL_CHAT_VALUES, COMPLETION, DOCUMENTED_CHAT_REJECTIONS


@pytest.mark.parametrize("stream", [False, True], ids=["chat", "stream"])
@pytest.mark.parametrize(
    ("provider_name", "parameter"),
    [
        (name, parameter)
        for name, parameters in DOCUMENTED_CHAT_REJECTIONS.items()
        for parameter in sorted(parameters)
    ],
)
async def test_documented_parameter_rejected_individually(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: ProviderName,
    parameter: str,
    stream: bool,
) -> None:
    upstream.post("/chat/completions").respond(200, json=COMPLETION)
    body = {
        "model": f"{provider_name}/model",
        "messages": CANONICAL_CHAT_VALUES["messages"],
        "stream": stream,
        parameter: CANONICAL_CHAT_VALUES[parameter],
    }
    if parameter == "top_logprobs":
        # Canonical validation requires logprobs=True. Allow that prerequisite so it
        # cannot mask a missing top_logprobs rejection, then restore via monkeypatch.
        body["logprobs"] = True
        monkeypatch.setattr(
            GroqAdapter,
            "capabilities",
            replace(
                GroqAdapter.capabilities,
                unsupported_parameters=GroqAdapter.capabilities.unsupported_parameters
                - {"logprobs"},
            ),
        )

    response = await client.post("/v1/chat/completions", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert f"'{parameter}'" in response.json()["error"]["message"]
    assert provider_name in response.json()["error"]["message"]
    assert not upstream.calls


@pytest.mark.parametrize("stream", [False, True], ids=["chat", "stream"])
@pytest.mark.parametrize(
    ("provider_name", "fields", "parameter"),
    [
        pytest.param("groq", {"n": 2}, "n (only 1 is supported)", id="groq-multiple_choices"),
        pytest.param(
            "groq",
            {"messages": [{"role": "user", "content": "Hi", "name": "u"}]},
            "messages[].name",
            id="groq-message_names",
        ),
        pytest.param(
            "deepseek",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "result"},
                }
            },
            "response_format.json_schema",
            id="deepseek-json_schema",
        ),
        pytest.param(
            "deepseek",
            {"max_tokens": 10, "max_completion_tokens": 20},
            "max_completion_tokens with max_tokens",
            id="deepseek-conflicting_limits",
        ),
    ],
)
async def test_capability_rejected_individually(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    fields: dict[str, Any],
    parameter: str,
    stream: bool,
) -> None:
    upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": CANONICAL_CHAT_VALUES["messages"],
            "stream": stream,
            **fields,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert f"'{parameter}'" in response.json()["error"]["message"]
    assert not upstream.calls


@pytest.mark.parametrize("provider_name", ["groq", "deepseek"])
async def test_missing_embedding_endpoint_rejected_individually(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    upstream.post("/embeddings").respond(200, json={})

    response = await client.post(
        "/v1/embeddings",
        json={
            "model": f"{provider_name}/embedding",
            "input": "Hi",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert "'embeddings'" in response.json()["error"]["message"]
    assert not upstream.calls
