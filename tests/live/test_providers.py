import asyncio
from typing import Any

import httpx
import pytest

from llm_gateway.usage.record import UsageRecord
from tests.fixtures import parse_events
from tests.live.models import NVIDIA_KIMI, LiveProvider

pytestmark = pytest.mark.live


async def test_live_chat(
    live_provider: LiveProvider, live_client: httpx.AsyncClient, live_records: list[UsageRecord]
) -> None:
    response = await _chat(
        live_provider,
        live_client,
        {
            "model": f"{live_provider.name}/{live_provider.chat_model}",
            "messages": [{"role": "user", "content": "Reply only with OK."}],
            **(
                {"max_tokens": 1024, "reasoning_effort": "low"}
                if live_provider.name in ("zai", "nvidia")
                else {}
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"].startswith(f"{live_provider.name}/")
    assert body["choices"][0]["message"]["content"]
    record = await _record(live_records)
    assert record.cost_status == ("unpriced" if live_provider.name == "nvidia" else "priced")
    assert (record.cost_usd is None) == (live_provider.name == "nvidia")
    assert record.prompt_tokens is not None
    assert record.prompt_tokens > 0


async def test_live_stream_with_usage(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
    live_records: list[UsageRecord],
) -> None:
    response = await _chat(
        live_provider,
        live_client,
        {
            "model": f"{live_provider.name}/{live_provider.chat_model}",
            "messages": [{"role": "user", "content": "Reply only with OK."}],
            "stream": True,
            "stream_options": {"include_usage": True},
            **(
                {"max_tokens": 1024, "reasoning_effort": "low"}
                if live_provider.name in ("zai", "nvidia")
                else {}
            ),
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
    assert record.cost_status == ("unpriced" if live_provider.name == "nvidia" else "priced")
    assert (record.cost_usd is None) == (live_provider.name == "nvidia")
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


@pytest.mark.slow
@pytest.mark.parametrize("live_provider", [NVIDIA_KIMI], indirect=True, ids=["nvidia-kimi-history"])
async def test_live_kimi_multi_turn_replays_complete_assistant_message(
    live_provider: LiveProvider,
    live_client: httpx.AsyncClient,
    live_records: list[UsageRecord],
) -> None:
    if live_provider.chat_model != NVIDIA_KIMI.chat_model:
        pytest.skip("Kimi history requires the Kimi model; unset GATEWAY_LIVE_NVIDIA_CHAT_MODEL")
    first_user = {"role": "user", "content": "Reply only with OK."}
    payload = {
        "model": f"nvidia/{NVIDIA_KIMI.chat_model}",
        "max_tokens": 1024,
        "reasoning_effort": "low",
    }

    first = await _chat(live_provider, live_client, {**payload, "messages": [first_user]})
    assert first.status_code == 200
    assistant = first.json()["choices"][0]["message"]
    assert assistant["role"] == "assistant"
    assert isinstance(assistant.get("reasoning_content"), str)
    assert bool(assistant["reasoning_content"])
    second = await _chat(
        live_provider,
        live_client,
        {
            **payload,
            "messages": [
                first_user,
                assistant,
                {"role": "user", "content": "Again, reply only with OK."},
            ],
        },
    )

    assert second.status_code == 200
    assert bool(second.json()["choices"][0]["message"]["content"])
    for index in (0, 1):
        record = await _record(live_records, index)
        assert record.provider == "nvidia"
        assert record.model == NVIDIA_KIMI.chat_model
        assert record.cost_status == "unpriced"
        assert record.cost_usd is None


async def _chat(
    provider: LiveProvider, client: httpx.AsyncClient, payload: dict[str, Any]
) -> httpx.Response:
    # ASGITransport does not enforce HTTPX read timeouts itself; bound each test call too.
    async with asyncio.timeout(provider.request_timeout_s):
        return await client.post("/v1/chat/completions", json=payload)


async def _record(records: list[UsageRecord], index: int = 0) -> UsageRecord:
    # A successful response may follow failed attempts; each keeps its own receipt.
    async with asyncio.timeout(2):
        while True:
            successful = [record for record in records if record.outcome == "success"]
            if len(successful) > index:
                return successful[index]
            await asyncio.sleep(0.001)
