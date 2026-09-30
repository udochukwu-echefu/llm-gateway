"""Kimi's explicit restrictions must not reject another NVIDIA-hosted model."""

import json

import pytest
import respx

from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import hosted_completion

pytestmark = pytest.mark.parametrize("provider_name", ["nvidia"])


@pytest.mark.parametrize("model", ["z-ai/glm-5.3", "z-ai/glm-5.3-flash"])
@pytest.mark.parametrize("parameter", ["top_p", "frequency_penalty", "presence_penalty", "n"])
async def test_glm_sampling_parameters_are_forwarded(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, model: str, parameter: str
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=hosted_completion(model))
    value = 1 if parameter == "n" else 0.5

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": f"nvidia/{model}",
            "messages": [{"role": "user", "content": "Hi"}],
            parameter: value,
        },
    )

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)[parameter] == value


@pytest.mark.parametrize("model", ["z-ai/glm-5.3", "z-ai/glm-5.3-flash"])
@pytest.mark.parametrize("role", ["developer", "system", "assistant"])
async def test_glm_does_not_inherit_kimi_content_array_restriction(
    hosted_gateway: HostedGateway, upstream: respx.MockRouter, model: str, role: str
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=hosted_completion(model))
    message = {"role": role, "content": [{"type": "text", "text": "Hi"}]}

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={"model": f"nvidia/{model}", "messages": [message]},
    )

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)["messages"] == [message]


@pytest.mark.parametrize("parameter", ["top_p", "frequency_penalty", "presence_penalty", "n"])
@pytest.mark.parametrize("value", [None, 1])
@pytest.mark.parametrize("stream", [False, True])
async def test_kimi_rejects_its_fixed_sampling_parameters_before_network(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    parameter: str,
    value: int | None,
    stream: bool,
) -> None:
    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={
            "model": "nvidia/moonshotai/kimi-k3",
            "messages": [{"role": "user", "content": "Hi"}],
            parameter: value,
            "stream": stream,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls
