import json

import httpx
import respx

from llm_gateway.schemas.common import ProviderName
from tests.fixtures import COMPLETION


async def test_undocumented_parameter_is_forwarded(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)
    # safety_identifier is undocumented on the compatible providers; OpenAI documents it.
    body = {
        "model": f"{provider_name}/model",
        "messages": [{"role": "user", "content": "Hi"}],
        "safety_identifier": "opaque-user",
    }

    response = await client.post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    assert json.loads(route.calls.last.request.content)["safety_identifier"] == "opaque-user"


async def test_provider_rejection_of_undocumented_parameter_passes_message_through(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    message = "safety_identifier is not supported by this model"
    route = upstream.post("/chat/completions").respond(400, json={"error": {"message": message}})

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "safety_identifier": "opaque-user",
        },
    )

    assert route.called
    assert response.status_code == 400
    assert response.json()["error"]["message"] == message
    assert response.json()["error"]["code"] == "upstream_rejected_request"
