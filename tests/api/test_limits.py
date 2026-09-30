"""Limits through HTTP, with a real Redis and mocked providers."""

import time
from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
import respx
from redis.asyncio import Redis

from llm_gateway.catalog import Catalog
from llm_gateway.config import Settings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from llm_gateway.tenants.repository import KeyRecord
from tests.conftest import MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION, STREAM, sse

pytestmark = pytest.mark.redis


@pytest.fixture
async def limited_client(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
) -> AsyncIterator[tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService]]:
    record = next(iter(memory_repository.records.values()))
    memory_repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(rpm=2, tpm=10, max_concurrency=1)
    )
    service = LimitService(test_redis, rpm_burst=2)
    slot = int(time.time() // 60)
    await test_redis.delete(*(f"lgw:auth-fail:127.0.0.1:{slot - offset}" for offset in (0, 1)))
    app = create_app(
        settings, key_repository=memory_repository, catalog=test_catalog, limit_service=service
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        yield client, memory_repository, service


async def test_success_headers_and_rpm_rejection(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
    upstream: respx.MockRouter,
) -> None:
    client, repository, _ = limited_client
    record = next(iter(repository.records.values()))
    repository.records[record.key_id] = replace(
        record, limits=LimitOverrides(rpm=2, tpm=100, max_concurrency=1)
    )
    upstream.post("/chat/completions").respond(200, json=COMPLETION)

    first = await client.post("/v1/chat/completions", json=CHAT_REQUEST)
    second = await client.post("/v1/chat/completions", json=CHAT_REQUEST)
    third = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit-requests"] == "2"
    assert first.headers["x-ratelimit-remaining-requests"] == "1"
    assert first.headers["x-ratelimit-limit-tokens"] == "100"
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limit_exceeded"
    assert int(third.headers["retry-after"]) > 0


async def test_actual_tokens_are_recorded_only_after_response(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
    upstream: respx.MockRouter,
) -> None:
    client, repository, service = limited_client
    record = next(iter(repository.records.values()))
    upstream.post("/chat/completions").respond(200, json=COMPLETION)

    first = await client.post("/v1/chat/completions", json=CHAT_REQUEST)
    second = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert first.status_code == 200
    assert first.headers["x-ratelimit-remaining-tokens"] == "10"
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limit_exceeded"
    assert (await service.window(str(record.team_id), "tokens", 10, 0, False))[0] == 0


async def test_21st_failed_authentication_never_queries_repository(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
    monkeypatch: pytest.MonkeyPatch,
    issued_test_key: str,
) -> None:
    client, repository, _ = limited_client
    public, key_id, secret = issued_test_key.split("_", 2)
    wrong_secret = ("A" if secret[0] != "A" else "B") + secret[1:]
    invalid_header = {"authorization": f"Bearer {public}_{key_id}_{wrong_secret}"}
    for _ in range(20):
        response = await client.get("/v1/models", headers=invalid_header)
        assert response.status_code == 401

    async def unexpected_lookup(key_id: str) -> KeyRecord | None:
        raise AssertionError("repository lookup after IP is limited")

    monkeypatch.setattr(repository, "get_key", unexpected_lookup)
    blocked = await client.get("/v1/models", headers=invalid_header)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limit_exceeded"
    assert int(blocked.headers["retry-after"]) > 0


async def test_valid_key_does_not_erase_ip_failure_count(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
    issued_test_key: str,
) -> None:
    client, _, _ = limited_client
    prefix, key_id, secret = issued_test_key.split("_", 2)
    wrong = ("A" if secret[0] != "A" else "B") + secret[1:]
    invalid_header = {"authorization": f"Bearer {prefix}_{key_id}_{wrong}"}
    for _ in range(19):
        assert (await client.get("/v1/models", headers=invalid_header)).status_code == 401

    valid = await client.get("/v1/models")
    twentieth = await client.get("/v1/models", headers=invalid_header)
    blocked = await client.get("/v1/models", headers=invalid_header)

    assert valid.status_code == 200
    assert twentieth.status_code == 401
    assert blocked.status_code == 429


@pytest.mark.parametrize("scenario", ["normal", "stream", "upstream_error"])
async def test_lease_released_after_response_finishes(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
    upstream: respx.MockRouter,
    test_redis: Redis,
    scenario: str,
) -> None:
    client, repository, _ = limited_client
    record = next(iter(repository.records.values()))
    repository.records[record.key_id] = replace(record, limits=LimitOverrides(max_concurrency=1))
    if scenario == "stream":
        upstream.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"".join(sse(*STREAM, "[DONE]")),
            )
        )
    elif scenario == "upstream_error":
        upstream.post("/chat/completions").respond(500)
    else:
        upstream.post("/chat/completions").respond(200, json=COMPLETION)

    response = await client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": scenario == "stream"}
    )

    assert response.status_code == (502 if scenario == "upstream_error" else 200)
    assert await test_redis.zcard(f"lgw:leases:{record.team_id}") == 0


@pytest.mark.parametrize(("mode", "expected"), [("open", 200), ("closed", 503)])
async def test_readiness_redis_outage_respects_failure_mode(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: int,
) -> None:
    async def unavailable() -> None:
        raise ConnectionError("simulated Redis outage")

    monkeypatch.setattr(test_redis, "ping", unavailable)
    app_settings = settings.model_copy(
        update={"limits": settings.limits.model_copy(update={"fail_mode": mode})}
    )
    app = create_app(
        app_settings,
        key_repository=memory_repository,
        catalog=test_catalog,
        limit_service=LimitService(test_redis, fail_mode=mode),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.get("/readyz")

    assert response.status_code == expected
    if mode == "closed":
        assert response.json()["error"]["code"] == "limits_unavailable"
    else:
        assert response.json() == {"status": "ok", "redis": "unavailable"}


async def test_readiness_reports_healthy_redis(
    limited_client: tuple[httpx.AsyncClient, MemoryKeyRepository, LimitService],
) -> None:
    client, _, _ = limited_client

    response = await client.get("/readyz")

    assert response.json() == {"status": "ok", "redis": "ok"}


@pytest.mark.parametrize(("mode", "status"), [("open", 200), ("closed", 503)])
async def test_authenticated_response_keeps_headers_when_redis_fails(
    test_redis: Redis,
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    status: int,
) -> None:
    service = LimitService(test_redis, fail_mode=mode)
    original_call = service.scripts.call

    async def broken_after_ip(
        name: str,
        keys: list[str],
        args: list[str | int | float],
    ) -> list[int] | int:
        if name == "window" and keys[0].startswith("lgw:auth-fail:"):
            return await original_call(name, keys, args)
        raise ConnectionError("simulated Redis outage after authentication")

    monkeypatch.setattr(service.scripts, "call", broken_after_ip)
    app_settings = settings.model_copy(
        update={"limits": settings.limits.model_copy(update={"fail_mode": mode})}
    )
    app = create_app(
        app_settings, key_repository=memory_repository, catalog=test_catalog, limit_service=service
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("192.0.2.88", 50000)),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        response = await client.get("/v1/models")

    assert response.status_code == status
    assert response.headers["x-ratelimit-limit-requests"] == "0"
    assert response.headers["x-ratelimit-remaining-requests"] == "unavailable"
