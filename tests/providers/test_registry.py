import httpx
import pytest
import respx

from llm_gateway.schemas.common import ProviderName


@pytest.mark.parametrize(
    ("model", "reason"),
    [
        ("unprefixed", "prefix"),
        ("unknown/model", "Unknown provider"),
        ("groq/", "Missing model"),
        ("openai/model", "not configured"),
    ],
)
@pytest.mark.parametrize("provider_name", ["groq"])
@pytest.mark.parametrize("endpoint", ["chat/completions", "embeddings"])
async def test_invalid_model_has_actionable_404(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    model: str,
    reason: str,
    endpoint: str,
) -> None:
    body = (
        {"messages": [{"role": "user", "content": "Hi"}]}
        if endpoint.startswith("chat")
        else {"input": "Hi"}
    )

    response = await client.post(f"/v1/{endpoint}", json={"model": model, **body})

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["code"] == "model_not_found"
    assert reason in error["message"]
    assert "Configured providers: groq" in error["message"]
    assert not upstream.calls


async def test_slashes_in_model_are_preserved(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    import json

    from tests.fixtures import COMPLETION

    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/vendor/model",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )

    assert json.loads(route.calls.last.request.content)["model"] == "vendor/model"
