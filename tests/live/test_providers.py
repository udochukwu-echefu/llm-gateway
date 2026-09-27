import asyncio

import httpx
import pytest

from llm_gateway.usage.record import UsageRecord
from tests.fixtures import parse_events
from tests.live.models import LiveProvider

pytestmark = pytest.mark.live


async def test_live_chat(
    live_provider: LiveProvider, live_client: httpx.AsyncClient, live_records: list[UsageRecord]
) -> None:
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
    record = await _record(live_records)
    assert record.cost_status == "priced"
    assert record.cost_usd is not None
    assert record.prompt_tokens is not None
    assert record.prompt_tokens > 0


async def test_live_stream_with_usage(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
    live_records: list[UsageRecord],
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
    record = await _record(live_records)
    assert record.cost_status == "priced"
    assert record.cost_usd is not None
    assert record.prompt_tokens is not None
    assert record.prompt_tokens > 0


async def test_live_embeddings(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
    live_records: list[UsageRecord],
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
    record = await _record(live_records)
    assert record.model == live_provider.embedding_model
    if live_provider.name == "gemini":
        # Google's OpenAI-compatible embedding response currently omits usage.
        assert record.cost_status == "usage_missing"
        assert record.cost_usd is None
        return
    assert record.cost_status == "priced"
    assert record.cost_usd is not None
    assert record.cost_usd > 0


async def _record(records: list[UsageRecord]) -> UsageRecord:
    # A successful response may follow failed attempts; each keeps its own receipt.
    async with asyncio.timeout(2):
        while True:
            for record in records:
                if record.outcome == "success":
                    return record
            await asyncio.sleep(0.001)
