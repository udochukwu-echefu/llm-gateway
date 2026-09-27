"""Opt-in paid smoke test; a second embedding must avoid the Gemini provider."""

import asyncio
import uuid

import httpx
import pytest

from llm_gateway.usage.record import UsageRecord
from tests.live.models import LiveProvider

pytestmark = pytest.mark.live


async def test_second_gemini_embedding_is_cached(
    live_provider: LiveProvider, live_client: httpx.AsyncClient, live_records: list[UsageRecord]
) -> None:
    if live_provider.name != "gemini":
        pytest.skip("Gemini embedding smoke test")
    assert live_provider.embedding_model is not None
    body = {
        "model": f"gemini/{live_provider.embedding_model}",
        "input": f"cache smoke {uuid.uuid4().hex}",
    }

    first = await live_client.post("/v1/embeddings", json=body)
    second = await live_client.post("/v1/embeddings", json=body)

    assert first.status_code == second.status_code == 200
    assert (first.headers["x-lgw-cache"], second.headers["x-lgw-cache"]) == ("miss", "hit")
    assert first.json() == second.json()
    for _ in range(50):
        if len(live_records) == 2:
            break
        await asyncio.sleep(0.01)
    assert [record.outcome for record in live_records] == ["success", "cache_hit"]
