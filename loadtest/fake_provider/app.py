"""Async fake upstream. Diagnostic counters distinguish completed calls from disconnects."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from loadtest.fake_provider.configuration import FakeSettings
from loadtest.fake_provider.responses import Sleep, completion, embeddings, stream


class ChatBody(BaseModel):
    model: str
    stream: bool = False
    stream_options: dict[str, bool] = Field(default_factory=dict)


class EmbeddingBody(BaseModel):
    model: str
    input: str | list[str] | list[int] | list[list[int]] = Field(min_length=1)
    dimensions: int = Field(default=8, ge=1, le=4096)


@dataclass
class Counts:
    started: int = 0
    completed: int = 0
    interrupted: int = 0


def create_app(settings: FakeSettings | None = None, *, sleep: Sleep = asyncio.sleep) -> FastAPI:
    config = settings if settings is not None else FakeSettings.from_environment()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    counts = Counts()

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/stats")
    async def stats() -> dict[str, int]:
        return vars(counts)

    @app.post("/v1/chat/completions", response_model=None)
    async def chat(body: ChatBody) -> dict[str, object] | StreamingResponse:
        counts.started += 1
        await sleep(config.latency_ms / 1000)
        if body.stream:
            return StreamingResponse(
                _counted_stream(body, config, counts, sleep), media_type="text/event-stream"
            )
        counts.completed += 1
        return completion(body.model)

    @app.post("/v1/embeddings")
    async def embed(body: EmbeddingBody) -> dict[str, object]:
        counts.started += 1
        await sleep(config.latency_ms / 1000)
        value = body.input
        count = len(value) if isinstance(value, list) and not isinstance(value[0], int) else 1
        counts.completed += 1
        return embeddings(body.model, count, body.dimensions)

    return app


async def _counted_stream(
    body: ChatBody, settings: FakeSettings, counts: Counts, sleep: Sleep
) -> AsyncIterator[bytes]:
    finished = False
    try:
        async for event in stream(
            body.model, settings, body.stream_options.get("include_usage", False), sleep
        ):
            yield event
        finished = True
        counts.completed += 1
    finally:
        if not finished:
            counts.interrupted += 1
