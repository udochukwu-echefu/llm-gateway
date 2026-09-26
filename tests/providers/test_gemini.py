import httpx
import pytest
import respx

pytestmark = pytest.mark.parametrize("provider_name", ["gemini"])


@pytest.mark.parametrize(
    "extra",
    [
        {"input": [1, 2]},
        {"input": [[1, 2]]},
        {"dimensions": 64},
        {"encoding_format": "base64"},
        {"user": "u"},
    ],
)
async def test_unverified_embedding_options_fail_locally(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/embeddings",
        json={
            "model": "gemini/embedding",
            "input": "hello",
            **extra,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls


@pytest.mark.parametrize("extra", [{"max_tokens": 10}, {"max_completion_tokens": 10}, {"n": 2}])
async def test_unverified_limits_fail_locally(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gemini/model",
            "messages": [{"role": "user", "content": "Hi"}],
            **extra,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls
