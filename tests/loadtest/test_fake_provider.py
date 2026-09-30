"""In-process synthetic provider tests: no real network or wall-clock assertions."""

import httpx
import pytest

from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk
from llm_gateway.schemas.embeddings import EmbeddingResponse
from loadtest.fake_provider.app import create_app
from loadtest.fake_provider.configuration import FakeSettings
from loadtest.fake_provider.responses import stream


async def test_chat_waits_configured_delay_without_echoing_input() -> None:
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    app = create_app(FakeSettings(latency_ms=123), sleep=sleep)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fake"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "private sentinel"}]},
        )
        stats = await client.get("/stats")

    parsed = ChatCompletion.model_validate_json(response.content)
    assert waits == [0.123]
    assert parsed.usage is not None
    assert parsed.usage.total_tokens == 30
    assert "private sentinel" not in response.text
    assert stats.json() == {"started": 1, "completed": 1, "interrupted": 0}


async def test_stream_has_twenty_chunks_usage_and_done_in_order() -> None:
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    app = create_app(FakeSettings(), sleep=sleep)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fake"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "test", "stream": True, "stream_options": {"include_usage": True}},
        )

    events = response.text.split("\n\n")
    chunks = [ChatCompletionChunk.model_validate_json(event[6:]) for event in events[:-2]]
    assert len(chunks) == 22
    assert all(chunk.choices[0].delta.content == "word " for chunk in chunks[:20])
    assert chunks[20].choices[0].finish_reason == "stop"
    assert chunks[21].usage is not None
    assert chunks[21].usage.total_tokens == 30
    assert events[-2] == "data: [DONE]"
    assert waits == [0.2] + [0.05] * 20


async def test_stream_can_omit_usage_and_be_closed_before_completion() -> None:
    iterator = stream("test", FakeSettings(chunk_count=2), False)

    first = await anext(iterator)
    await iterator.aclose()

    assert b"usage" not in first
    assert b"[DONE]" not in first


@pytest.mark.parametrize("value", ["text", [1, 2], ["one", "two"], [[1], [2]]])
async def test_embeddings_return_canonical_usage_and_dimensions(
    value: str | list[int] | list[str] | list[list[int]],
) -> None:
    async def sleep(delay: float) -> None:
        pass

    app = create_app(FakeSettings(), sleep=sleep)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fake"
    ) as client:
        response = await client.post(
            "/v1/embeddings", json={"model": "test", "input": value, "dimensions": 3}
        )

    parsed = EmbeddingResponse.model_validate_json(response.content)
    assert len(parsed.data) == (
        2 if isinstance(value, list) and not isinstance(value[0], int) else 1
    )
    assert parsed.data[0].embedding == [0.125] * 3
    assert parsed.usage is not None
    assert parsed.usage.prompt_tokens == len(parsed.data) * 10


async def test_empty_embeddings_are_rejected_before_counting_a_call() -> None:
    app = create_app(FakeSettings(latency_ms=0))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://fake"
    ) as client:
        response = await client.post("/v1/embeddings", json={"model": "test", "input": []})
        stats = await client.get("/stats")

    assert response.status_code == 422
    assert stats.json()["started"] == 0


def test_invalid_fake_configuration_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_LATENCY_MS", "-1")

    with pytest.raises(ValueError, match="latency_ms"):
        create_app()
