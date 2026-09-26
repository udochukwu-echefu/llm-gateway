import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from time import perf_counter

import anyio
import httpx
import pytest
import respx
from fastapi import FastAPI
from starlette.types import Message, Scope

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.usage.record import UsageRecord
from tests.conftest import MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION, EMBEDDINGS, STREAM, USAGE_CHUNK, sse


@pytest.fixture
def recorded_app(
    settings: Settings, memory_repository: MemoryKeyRepository, test_catalog: Catalog
) -> tuple[FastAPI, list[UsageRecord]]:
    records: list[UsageRecord] = []

    async def sink(batch: Sequence[UsageRecord]) -> None:
        records.extend(batch)

    app = create_app(
        settings.model_copy(update={"usage_batch_size": 1}),
        key_repository=memory_repository,
        catalog=test_catalog,
        usage_sink=sink,
    )
    return app, records


@pytest.fixture
async def recorded_client(
    recorded_app: tuple[FastAPI, list[UsageRecord]], issued_test_key: str
) -> AsyncIterator[httpx.AsyncClient]:
    app, _ = recorded_app
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        yield client


async def wait_for_record(records: list[UsageRecord]) -> UsageRecord:
    with anyio.fail_after(2):
        for _ in range(2000):
            if records:
                break
            await asyncio.sleep(0.001)
    return records[0]


async def test_success_has_exact_cost_and_no_private_text(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    prompt = "SENSITIVE_PRIVATE_PROMPT_8261"
    answer = "SENSITIVE_PRIVATE_ANSWER_2198"
    wire = {
        **COMPLETION,
        "choices": [
            {
                **COMPLETION["choices"][0],
                "message": {"role": "assistant", "content": answer},
            }
        ],
    }
    upstream.post("/chat/completions").respond(200, json=wire)

    response = await recorded_client.post(
        "/v1/chat/completions",
        json={**CHAT_REQUEST, "messages": [{"role": "user", "content": prompt}]},
    )
    record = await wait_for_record(recorded_app[1])

    assert response.status_code == 200
    assert record.cost_usd == Decimal("0.000000975")
    assert (record.outcome, record.cost_status, record.prompt_tokens, record.completion_tokens) == (
        "success",
        "priced",
        9,
        1,
    )
    assert record.duration_ms is not None
    assert record.ttfb_ms is not None
    assert prompt not in repr(record)
    assert answer not in repr(record)
    assert len(recorded_app[1]) == 1


async def test_uncatalogued_is_rejected_without_upstream_call_or_record(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    route = upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await recorded_client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "model": "groq/unknown"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert "catalogue" in response.json()["error"]["message"]
    assert not route.called
    assert not recorded_app[1]


async def test_model_list_only_shows_configured_catalogue_entries(
    recorded_client: httpx.AsyncClient,
) -> None:
    response = await recorded_client.get("/v1/models")

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert {item["owned_by"] for item in response.json()["data"]} == {"groq", "openai"}
    assert all(item["id"].startswith(f"{item['owned_by']}/") for item in response.json()["data"])


async def test_upstream_status_error_records_zero_not_billed(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").respond(429, json={"error": {"message": "slow"}})

    response = await recorded_client.post("/v1/chat/completions", json=CHAT_REQUEST)
    record = await wait_for_record(recorded_app[1])

    assert response.status_code == 429
    assert (record.outcome, record.cost_status, record.cost_usd) == (
        "upstream_error",
        "not_billed",
        Decimal(0),
    )


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (httpx.ConnectError("connection refused"), 502),
        (httpx.ConnectTimeout("connect timed out"), 504),
        (httpx.PoolTimeout("pool exhausted"), 503),
    ],
)
async def test_connect_phase_failure_is_not_billed(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
    failure: httpx.HTTPError,
    status: int,
) -> None:
    upstream.post("/chat/completions").mock(side_effect=failure)

    response = await recorded_client.post("/v1/chat/completions", json=CHAT_REQUEST)
    record = await wait_for_record(recorded_app[1])

    assert response.status_code == status
    assert (record.outcome, record.cost_status, record.cost_usd) == (
        "upstream_error",
        "not_billed",
        Decimal(0),
    )


async def test_read_timeout_keeps_unknown_billable_cost(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").mock(side_effect=httpx.ReadTimeout("after send"))

    response = await recorded_client.post("/v1/chat/completions", json=CHAT_REQUEST)
    record = await wait_for_record(recorded_app[1])

    assert response.status_code == 504
    assert (record.outcome, record.cost_status, record.cost_usd) == (
        "upstream_error",
        "usage_missing",
        None,
    )


async def test_missing_embedding_usage_keeps_null_cost(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/embeddings").respond(200, json={**EMBEDDINGS, "usage": None})

    response = await recorded_client.post(
        "/v1/embeddings", json={"model": "openai/text-embedding-004", "input": "hello"}
    )
    record = await wait_for_record(recorded_app[1])

    assert response.status_code == 200
    assert record.cost_status == "usage_missing"
    assert record.cost_usd is None


async def test_stream_cost_is_recorded_after_completion(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").mock(
        return_value=httpx.Response(200, content=b"".join(sse(*STREAM, USAGE_CHUNK, "[DONE]")))
    )

    response = await recorded_client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    )
    record = await wait_for_record(recorded_app[1])

    assert response.text.endswith("data: [DONE]\n\n")
    assert (record.outcome, record.cost_status, record.prompt_tokens, record.completion_tokens) == (
        "success",
        "priced",
        9,
        2,
    )


async def test_stream_error_is_recorded_without_inventing_usage(
    recorded_client: httpx.AsyncClient,
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").mock(
        return_value=httpx.Response(200, content=b"".join(sse(STREAM[0])))
    )

    response = await recorded_client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    )
    record = await wait_for_record(recorded_app[1])

    assert "upstream_stream_truncated" in response.text
    assert (record.outcome, record.cost_status, record.cost_usd) == (
        "stream_error",
        "usage_missing",
        None,
    )


async def test_disconnect_still_records_incomplete_stream(
    recorded_app: tuple[FastAPI, list[UsageRecord]],
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    class Stalled(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield sse(STREAM[0])[0]
            await anyio.sleep_forever()

        async def aclose(self) -> None:
            pass

    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, stream=Stalled()))
    body = json.dumps({**CHAT_REQUEST, "stream": True}).encode()
    first = anyio.Event()
    received = False

    async def receive() -> Message:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await first.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            first.set()

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {issued_test_key}".encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("gateway.test", 80),
    }
    app, records = recorded_app
    async with app.router.lifespan_context(app):
        with anyio.fail_after(5):
            await app(scope, receive, send)
        record = await wait_for_record(records)

    assert (record.outcome, record.cost_status, record.cost_usd) == (
        "client_disconnected",
        "stream_incomplete",
        None,
    )


async def test_full_usage_queue_does_not_delay_successful_requests(
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    entered = anyio.Event()
    release = anyio.Event()

    async def blocked_sink(records: Sequence[UsageRecord]) -> None:
        entered.set()
        await release.wait()

    app = create_app(
        settings.model_copy(update={"usage_queue_size": 1, "usage_batch_size": 1}),
        key_repository=memory_repository,
        catalog=test_catalog,
        usage_sink=blocked_sink,
    )
    upstream.post("/chat/completions").respond(200, json=COMPLETION)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        try:
            assert (await client.post("/v1/chat/completions", json=CHAT_REQUEST)).status_code == 200
            await entered.wait()
            assert (await client.post("/v1/chat/completions", json=CHAT_REQUEST)).status_code == 200
            started = perf_counter()
            with anyio.fail_after(0.5):
                response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)
            assert response.status_code == 200
            assert perf_counter() - started < 0.25
            assert app.state.gateway.usage_writer.dropped == 1
        finally:
            release.set()
