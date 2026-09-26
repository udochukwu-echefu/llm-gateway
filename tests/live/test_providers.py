import httpx
import pytest

from tests.fixtures import parse_events
from tests.live.models import LiveProvider

pytestmark = pytest.mark.live


async def test_live_chat(live_provider: LiveProvider, live_client: httpx.AsyncClient) -> None:
    response = await live_client.post(
        "/v1/chat/completions",
        json={
            "model": f"{live_provider.name}/{live_provider.chat_model}",
            "messages": [{"role": "user", "content": "Reply only with OK."}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"].startswith(f"{live_provider.name}/")
    assert body["choices"][0]["message"]["content"]


async def test_live_stream_with_usage(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
) -> None:
    response = await live_client.post(
        "/v1/chat/completions",
        json={
            "model": f"{live_provider.name}/{live_provider.chat_model}",
            "messages": [{"role": "user", "content": "Reply only with OK."}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    )

    assert response.status_code == 200
    events = parse_events(response.text)
    assert events[-1] == "[DONE]"
    assert all("error" not in event for event in events[:-1])
    assert any(
        event.get("usage", {}).get("total_tokens", 0) > 0
        for event in events[:-1]
        if event.get("usage")
    )


async def test_live_embeddings(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
) -> None:
    if live_provider.embedding_model is None:
        pytest.skip(f"{live_provider.name} does not support embeddings")

    response = await live_client.post(
        "/v1/embeddings",
        json={
            "model": f"{live_provider.name}/{live_provider.embedding_model}",
            "input": "hello",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["embedding"]
    assert response.json()["model"].startswith(f"{live_provider.name}/")
