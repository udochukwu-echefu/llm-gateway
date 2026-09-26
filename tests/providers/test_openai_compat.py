import json
from typing import Any

import httpx
import pytest
import respx
import structlog
from structlog.testing import capture_logs

from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.providers.registry import ADAPTER_TYPES
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.fixtures import COMPLETION, EMBEDDINGS, STREAM, USAGE_CHUNK, parse_events, prefixed, sse


@pytest.mark.parametrize("status", [200, 401])
@pytest.mark.parametrize("request_id", ["provider-request", None])
@pytest.mark.parametrize("stream", [False, True])
async def test_request_id_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    status: int,
    request_id: str | None,
    stream: bool,
) -> None:
    headers = {"x-request-id": request_id} if request_id else {}
    wire = b"".join(sse(*STREAM, "[DONE]")) if stream else json.dumps(COMPLETION).encode()
    upstream.post("/chat/completions").respond(status, content=wire, headers=headers)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await client.post(
            "/v1/chat/completions",
            json={
                "model": f"{provider_name}/model",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": stream,
            },
        )

    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["upstream_request_id"] == request_id


async def test_chat_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    body = {
        "model": f"{provider_name}/vendor/model",
        "messages": [{"role": "user", "content": "Hi"}],
    }

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post("/v1/chat/completions", json=body)

    assert response.json() == prefixed(COMPLETION, provider_name)
    assert json.loads(route.calls.last.request.content)["model"] == "vendor/model"
    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["provider"] == provider_name
    assert access["model"] == body["model"]
    assert access["total_tokens"] == 10


@pytest.mark.parametrize("include_usage", [True, False])
async def test_stream_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    include_usage: bool,
) -> None:
    route = upstream.post("/chat/completions").respond(
        200,
        content=b"".join(sse(*STREAM, USAGE_CHUNK, "[DONE]")),
    )
    body = {
        "model": f"{provider_name}/model",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": True,
        "stream_options": {"include_usage": include_usage},
    }

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post("/v1/chat/completions", json=body)

    expected = [prefixed(c, provider_name) for c in STREAM]
    if include_usage:
        expected.append(prefixed(USAGE_CHUNK, provider_name))
    assert parse_events(response.text) == [*expected, "[DONE]"]
    assert json.loads(route.calls.last.request.content)["stream_options"] == {"include_usage": True}
    assert next(entry for entry in logs if entry["event"] == "request")["total_tokens"] == 11


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("status", "expected", "code"),
    [
        (400, 400, "upstream_rejected_request"),
        (404, 404, "upstream_rejected_request"),
        (413, 413, "upstream_rejected_request"),
        (422, 422, "upstream_rejected_request"),
        (401, 502, "upstream_auth_failed"),
        (403, 502, "upstream_auth_failed"),
        (408, 504, "upstream_timeout"),
        (429, 429, "upstream_rate_limited"),
        (500, 502, "upstream_server_error"),
    ],
)
async def test_status_errors_precede_stream_headers(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    stream: bool,
    status: int,
    expected: int,
    code: str,
) -> None:
    upstream.post("/chat/completions").respond(status, headers={"retry-after": "3"})

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": stream,
        },
    )

    assert response.status_code == expected
    assert response.json()["error"]["code"] == code
    if status == 429:
        assert response.headers["retry-after"] == "3"


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (httpx.ConnectError, 502, "upstream_unavailable"),
        (httpx.ReadTimeout, 504, "upstream_timeout"),
        (httpx.PoolTimeout, 503, "gateway_overloaded"),
    ],
)
async def test_transport_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    exception: type[httpx.HTTPError],
    status: int,
    code: str,
) -> None:
    upstream.post("/chat/completions").mock(side_effect=exception("failure"))

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_only_serving_provider_options_are_sent(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    options = {name: {f"option_{name}": True} for name in ADAPTER_TYPES}

    await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "provider_options": options,
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert {key for key in sent if key.startswith("option_")} == {f"option_{provider_name}"}


async def test_developer_role_contract(
    adapter: OpenAICompatibleAdapter,
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    request = ChatCompletionRequest.model_validate(
        {
            "model": "model",
            "messages": [{"role": "developer", "content": "Instructions"}],
        }
    )

    await adapter.chat(request, "model")

    role = "developer" if adapter.capabilities.supports_developer else "system"
    assert json.loads(route.calls.last.request.content)["messages"][0]["role"] == role
    assert request.messages[0].role == "developer"


async def test_embedding_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    adapter: OpenAICompatibleAdapter,
) -> None:
    route = upstream.post("/embeddings").respond(200, json=EMBEDDINGS)

    response = await client.post(
        "/v1/embeddings",
        json={
            "model": f"{provider_name}/embedding",
            "input": "hello",
        },
    )

    if adapter.capabilities.supports_embeddings:
        assert response.json() == prefixed(EMBEDDINGS, provider_name)
        assert json.loads(route.calls.last.request.content)["model"] == "embedding"
    else:
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_parameter"
        assert not route.called


@pytest.mark.parametrize("stream", [False, True])
async def test_unsupported_parameters_fail_before_network(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    adapter: OpenAICompatibleAdapter,
    stream: bool,
) -> None:
    for parameter in adapter.capabilities.unsupported_parameters - {"messages[].name"}:
        values: dict[str, Any] = {
            "n": 2,
            "seed": 1,
            "max_tokens": 10,
            "max_completion_tokens": 10,
            "logprobs": True,
            "top_logprobs": 1,
            "logit_bias": {"1": 1},
            "frequency_penalty": 0.1,
            "presence_penalty": 0.1,
            "parallel_tool_calls": True,
            "service_tier": "auto",
            "user": "u",
            "safety_identifier": "u",
            "temperature": 1.0,
            "top_p": 0.5,
            "stop": "end",
        }
        body: dict[str, Any] = {
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": stream,
            parameter: values[parameter],
        }
        if parameter == "top_logprobs":
            body["logprobs"] = True

        response = await client.post("/v1/chat/completions", json=body)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_parameter"
        assert provider_name in response.json()["error"]["message"]
        assert not upstream.calls
