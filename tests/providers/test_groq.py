import httpx
import pytest
import respx

from tests.fixtures import COMPLETION, chunk, parse_events, sse

pytestmark = pytest.mark.parametrize("provider_name", ["groq"])


@pytest.mark.parametrize("stream", [False, True])
async def test_reasoning_is_normalized(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    stream: bool,
) -> None:
    message = {"content": "answer", "reasoning": "analysis"}
    response = (
        httpx.Response(200, content=b"".join(sse(chunk(message), "[DONE]")))
        if stream
        else httpx.Response(200, json={**COMPLETION, "choices": [{"index": 0, "message": message}]})
    )
    upstream.post("/chat/completions").mock(return_value=response)

    result = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": stream,
        },
    )

    body = parse_events(result.text)[0] if stream else result.json()
    output = body["choices"][0]["delta" if stream else "message"]
    assert output["reasoning_content"] == "analysis"
    assert "reasoning" not in output


@pytest.mark.parametrize(
    "extra", [{"n": 2}, {"messages": [{"role": "user", "content": "Hi", "name": "u"}]}]
)
async def test_restricted_values_rejected(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    extra: dict[str, object],
) -> None:
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "groq/model",
            "messages": [{"role": "user", "content": "Hi"}],
            **extra,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_parameter"
    assert not upstream.calls
