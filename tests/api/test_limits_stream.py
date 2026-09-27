"""The concurrency lease survives headers and chunks until stream disconnect."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import replace

import anyio
import httpx
import pytest
import respx
from redis.asyncio import Redis
from starlette.types import Message, Scope

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, STREAM, sse

pytestmark = pytest.mark.redis


@pytest.mark.parametrize(("lease_ttl", "hold_seconds"), [(900, 0), (2, 2.5)])
async def test_lease_is_held_after_headers_and_released_after_disconnect(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    upstream: respx.MockRouter,
    lease_ttl: int,
    hold_seconds: float,
) -> None:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(max_concurrency=1)
    )
    team = record.team_id
    service = LimitService(test_redis, lease_ttl=lease_ttl)
    slot = int(time.time() // 60)
    await test_redis.delete(*(f"lgw:auth-fail:127.0.0.1:{slot - offset}" for offset in (0, 1)))
    app = create_app(
        settings, key_repository=memory_repository, catalog=test_catalog, limit_service=service
    )

    class Stalled(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield sse(STREAM[0])[0]
            await anyio.sleep_forever()

        async def aclose(self) -> None:
            pass

    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, stream=Stalled()))
    body = json.dumps({**CHAT_REQUEST, "stream": True}).encode()
    disconnect = anyio.Event()
    first_chunk = anyio.Event()
    received = False
    held_at_headers = False
    held_at_chunk = False
    status = 0
    response_body = b""

    async def receive() -> Message:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal held_at_headers, held_at_chunk, status, response_body
        if message["type"] == "http.response.start":
            status = message["status"]
            held_at_headers = await test_redis.zcard(f"lgw:leases:{team}") == 1
        if message["type"] == "http.response.body" and message.get("body"):
            response_body += message["body"]
            held_at_chunk = await test_redis.zcard(f"lgw:leases:{team}") == 1
            first_chunk.set()
            if not hold_seconds:
                disconnect.set()

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
    async with app.router.lifespan_context(app):
        with anyio.fail_after(5):
            if hold_seconds:
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(app(scope, receive, send))
                    await first_chunk.wait()
                    await asyncio.sleep(hold_seconds)
                    assert await test_redis.zcard(f"lgw:leases:{team}") == 1
                    disconnect.set()
            else:
                await app(scope, receive, send)

    assert status == 200, response_body
    assert held_at_headers
    assert held_at_chunk
    assert await test_redis.zcard(f"lgw:leases:{team}") == 0
