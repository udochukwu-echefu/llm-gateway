import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

import httpx
import pytest
import respx
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from starlette.types import Scope
from structlog.testing import capture_logs

from llm_gateway.errors import error_body
from llm_gateway.gateway_state import get_app_state
from llm_gateway.tenants.keys import issue_key
from tests.conftest import TEST_PEPPER, MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION


class _IncludeContext(Protocol):
    prefix: str


class _IncludedRoute(Protocol):
    include_context: _IncludeContext


def routes(app: FastAPI) -> list[str]:
    def collect(router: APIRouter, prefix: str = "") -> list[str]:
        paths: list[str] = []
        for route in router.routes:
            if isinstance(route, APIRoute):
                paths.append(prefix + route.path)
            else:
                nested = getattr(route, "original_router", None)
                if isinstance(nested, APIRouter):
                    context = cast(_IncludedRoute, route).include_context
                    paths.extend(collect(nested, prefix + str(context.prefix)))
        return paths

    return [path for path in collect(app.router) if path.startswith("/v1/")]


@pytest.mark.parametrize("endpoint", ["/v1/chat/completions", "/v1/embeddings"])
async def test_every_v1_route_requires_authentication(app: FastAPI, endpoint: str) -> None:
    assert set(routes(app)) == {"/v1/chat/completions", "/v1/embeddings"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as anonymous,
    ):
        response = await anonymous.post(endpoint, content=b"x" * (2 * 1024 * 1024))

    assert response.status_code == 401
    assert response.json() == error_body(
        "Invalid API key.", type="invalid_request_error", code="invalid_api_key"
    )


async def test_authentication_does_not_read_anonymous_body(app: FastAPI) -> None:
    from starlette.types import Message

    responses: list[Message] = []

    async def receive() -> Message:
        raise AssertionError("unauthenticated body was read")

    async def send(message: Message) -> None:
        responses.append(message)

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
        "headers": [],
        "client": ("127.0.0.1", 40000),
        "server": ("gateway.test", 80),
    }

    async with app.router.lifespan_context(app):
        await app(scope, receive, send)

    assert responses[0]["status"] == 401


@pytest.mark.parametrize(
    "failure", ["missing", "scheme", "malformed", "unknown", "wrong", "revoked", "expired"]
)
@pytest.mark.parametrize("endpoint", ["/v1/chat/completions", "/v1/embeddings"])
async def test_authentication_failures_share_one_response(
    client: httpx.AsyncClient,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    failure: str,
    endpoint: str,
) -> None:
    _, key_id, secret = issued_test_key.split("_", 2)
    headers: dict[str, str] = {}
    if failure == "missing":
        headers["authorization"] = ""
    elif failure == "scheme":
        headers["authorization"] = f"Basic {issued_test_key}"
    elif failure == "malformed":
        headers["authorization"] = "Bearer lgw_bad"
    elif failure == "unknown":
        headers["authorization"] = f"Bearer lgw_aaaaaaaaaaaa_{secret}"
    elif failure == "wrong":
        other = issue_key(TEST_PEPPER.encode()).full_key.split("_", 2)[2]
        headers["authorization"] = f"Bearer lgw_{key_id}_{other}"
    else:
        original = memory_repository.records[key_id]
        memory_repository.records[key_id] = replace(
            original,
            **(
                {"revoked_at": datetime.now(UTC)}
                if failure == "revoked"
                else {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
            ),
        )

    response = await client.post(endpoint, content=b"not valid JSON", headers=headers)

    assert response.status_code == 401
    assert response.json() == error_body(
        "Invalid API key.", type="invalid_request_error", code="invalid_api_key"
    )


async def test_authenticated_request_annotates_identity_without_logging_secret(
    client: httpx.AsyncClient,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    upstream: respx.MockRouter,
) -> None:
    upstream.post("/chat/completions").respond(200, json=COMPLETION)
    key_id = issued_test_key.split("_")[1]
    record = memory_repository.records[key_id]

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 200
    access = next(log for log in logs if log["event"] == "request")
    assert access["organization_id"] == str(record.organization_id)
    assert access["team_id"] == str(record.team_id)
    assert access["key_id"] == key_id
    assert all(issued_test_key.split("_", 2)[2] not in json.dumps(log) for log in logs)


async def test_revoked_key_stops_working_after_cache_ttl(
    client: httpx.AsyncClient,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    app: FastAPI,
) -> None:
    clock = [0.0]
    get_app_state(app).key_cache.clock = lambda: clock[0]
    key_id = issued_test_key.split("_")[1]
    await client.post("/v1/chat/completions", json={})
    record = memory_repository.records[key_id]
    memory_repository.records[key_id] = replace(record, revoked_at=datetime.now(UTC))

    within_ttl = await client.post("/v1/chat/completions", json={})
    clock[0] = 30
    after_ttl = await client.post("/v1/chat/completions", json={})

    assert within_ttl.status_code == 400  # authenticated, body rejected
    assert after_ttl.status_code == 401


async def test_continuous_use_does_not_extend_revoked_keys_cache_ttl(
    client: httpx.AsyncClient,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    app: FastAPI,
) -> None:
    clock = [0.0]
    get_app_state(app).key_cache.clock = lambda: clock[0]
    key_id = issued_test_key.split("_")[1]

    first = await client.post("/v1/chat/completions", json={})
    memory_repository.records[key_id] = replace(
        memory_repository.records[key_id], revoked_at=datetime.now(UTC)
    )
    clock[0] = 20
    within_ttl = await client.post("/v1/chat/completions", json={})
    clock[0] = 35
    after_ttl = await client.post("/v1/chat/completions", json={})

    assert first.status_code == 400
    assert within_ttl.status_code == 400
    assert after_ttl.status_code == 401


async def test_wrong_secret_is_never_cached(
    client: httpx.AsyncClient,
    memory_repository: MemoryKeyRepository,
    issued_test_key: str,
    app: FastAPI,
) -> None:
    _, key_id, secret = issued_test_key.split("_", 2)
    memory_repository.records.pop(key_id)

    failed = await client.post(
        "/v1/chat/completions", headers={"authorization": f"Bearer {issued_test_key}"}
    )
    assert key_id not in get_app_state(app).key_cache.entries
    import uuid

    from llm_gateway.tenants.keys import hash_secret
    from llm_gateway.tenants.repository import KeyRecord

    memory_repository.records[key_id] = KeyRecord(
        key_id, hash_secret(TEST_PEPPER.encode(), secret), uuid.uuid4(), uuid.uuid4()
    )
    recovered = await client.post("/v1/chat/completions", json={})

    assert failed.status_code == 401
    assert recovered.status_code == 400


async def test_wrong_secret_for_existing_key_is_not_cached(
    client: httpx.AsyncClient, issued_test_key: str, app: FastAPI
) -> None:
    _, key_id, _ = issued_test_key.split("_", 2)
    wrong = issue_key(TEST_PEPPER.encode()).full_key.split("_", 2)[2]

    response = await client.post(
        "/v1/embeddings", headers={"authorization": f"Bearer lgw_{key_id}_{wrong}"}
    )

    assert response.status_code == 401
    assert key_id not in get_app_state(app).key_cache.entries


async def test_cached_key_still_expires_at_absolute_deadline(
    client: httpx.AsyncClient, memory_repository: MemoryKeyRepository, issued_test_key: str
) -> None:
    key_id = issued_test_key.split("_")[1]
    memory_repository.records[key_id] = replace(
        memory_repository.records[key_id],
        expires_at=datetime.now(UTC) + timedelta(milliseconds=200),
    )
    first = await client.post("/v1/chat/completions", json={})
    import asyncio

    await asyncio.sleep(0.25)
    expired = await client.post("/v1/chat/completions", json={})

    assert first.status_code == 400
    assert expired.status_code == 401


async def test_unverified_key_id_and_secret_never_appear_in_logs(client: httpx.AsyncClient) -> None:
    unknown = issue_key(TEST_PEPPER.encode())

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post(
            "/v1/embeddings", headers={"authorization": f"Bearer {unknown.full_key}"}
        )

    assert response.status_code == 401
    assert all(log.get("key_id") is None for log in logs)
    assert all(unknown.full_key not in json.dumps(log) for log in logs)
