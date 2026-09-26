import re

import httpx
import pytest
import respx
import structlog
from fastapi import FastAPI
from structlog.testing import capture_logs

from tests.fixtures import CHAT_REQUEST, COMPLETION


async def test_request_id_is_generated_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_valid_incoming_request_id_is_kept(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "trace-abc.123"})

    assert response.headers["x-request-id"] == "trace-abc.123"


@pytest.mark.parametrize("bad_id", ["has space", "x" * 129, "semi;colon"])
async def test_invalid_incoming_request_id_is_replaced(
    client: httpx.AsyncClient, bad_id: str
) -> None:
    response = await client.get("/healthz", headers={"x-request-id": bad_id})

    assert response.headers["x-request-id"] != bad_id


async def test_unhandled_exception_becomes_a_500_with_request_id(app: FastAPI) -> None:
    @app.get("/boom")
    async def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("secret internal detail")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "x-request-id" in response.headers


async def test_access_log_has_context_but_never_prompt_content(
    client: httpx.AsyncClient, upstream: respx.MockRouter
) -> None:
    upstream.post("/chat/completions").respond(
        200, json=COMPLETION, headers={"x-request-id": "req_upstream_1"}
    )

    # merge_contextvars adds the request-scoped fields, as the real configuration does.
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        response = await client.post(
            "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-request-id": "trace-1"}
        )

    access = next(entry for entry in logs if entry["event"] == "request")
    assert access["request_id"] == "trace-1"
    assert access["status"] == 200
    assert access["model"] == CHAT_REQUEST["model"]
    assert access["upstream_request_id"] == "req_upstream_1"
    assert access["provider"] == "groq"
    assert access["completed"] is True
    assert isinstance(access["duration_ms"], float)
    assert response.status_code == 200
    # Prompts and completions can hold personal data; step 1 never logs bodies.
    assert "Say hi" not in repr(logs)
    assert "hi" not in [str(value) for entry in logs for value in entry.values()]
