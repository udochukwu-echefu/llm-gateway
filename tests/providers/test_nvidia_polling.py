"""Accepted jobs are polled once per invocation, bounded and locally cancellable."""

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from starlette.types import Message, Scope

from llm_gateway.config import Settings
from llm_gateway.providers import nvidia_polling
from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import NVIDIA_MODELS, hosted_completion

pytestmark = pytest.mark.parametrize("provider_name", ["nvidia"])
REQUEST_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
CHAT = {"model": "nvidia/moonshotai/kimi-k3", "messages": [{"role": "user", "content": "Hi"}]}


@pytest.fixture
def hosted_max_retries() -> int:
    return 2


@pytest.fixture(autouse=True)
def immediate_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nvidia_polling, "POLL_INTERVAL_S", 0)


async def test_accepted_kimi_is_polled_on_same_authenticated_endpoint(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})
    poll = upstream.get(f"/status/{REQUEST_ID}").mock(
        side_effect=[
            httpx.Response(202, json={}),
            httpx.Response(200, json=hosted_completion("moonshotai/kimi-k3")),
        ]
    )

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    assert response.status_code == 200
    assert response.json()["model"] == CHAT["model"]
    assert post.call_count == 1
    assert poll.call_count == 2
    assert (
        poll.calls.last.request.headers["authorization"]
        == post.calls.last.request.headers["authorization"]
    )
    assert poll.calls.last.request.url.host == post.calls.last.request.url.host
    assert len(hosted_gateway.records) == 1
    assert hosted_gateway.records[0].cost_status == "unpriced"
    assert hosted_gateway.records[0].prompt_tokens == 20


@pytest.mark.parametrize("request_id", [None, "../../other", "https://evil.invalid/", "not-a-uuid"])
async def test_missing_or_invalid_request_id_is_rejected_without_polling(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    request_id: str | None,
) -> None:
    post = upstream.post("/chat/completions").respond(
        202,
        headers={"NVCF-REQID": request_id} if request_id else {},
    )

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_invalid_response"
    assert post.call_count == 1
    assert len(upstream.calls) == 1


@pytest.mark.parametrize(
    ("model", "stream"),
    [
        (model, stream)
        for model in NVIDIA_MODELS
        for stream in (False, True)
        if model != "moonshotai/kimi-k3" or stream
    ],
)
async def test_undocumented_queued_modes_return_clear_retryable_error(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    model: str,
    stream: bool,
) -> None:
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={**CHAT, "model": f"nvidia/{model}", "stream": stream},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_pending_unsupported"
    assert post.call_count == 3
    assert len(upstream.calls) == 3


@pytest.mark.parametrize("status", [422, 500])
async def test_poll_failure_does_not_resubmit_an_accepted_job(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    status: int,
) -> None:
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})
    poll = upstream.get(f"/status/{REQUEST_ID}").respond(status, json={"message": "Failed"})

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)

    assert response.status_code == (422 if status == 422 else 502)
    assert post.call_count == poll.call_count == 1


async def test_poll_transport_failure_does_not_resubmit_an_accepted_job(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})
    poll = upstream.get(f"/status/{REQUEST_ID}").mock(side_effect=httpx.ConnectError("offline"))

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    assert response.status_code == 502
    assert post.call_count == poll.call_count == 1
    assert hosted_gateway.records[0].cost_status == "usage_missing"


async def test_poll_body_timeout_does_not_resubmit_even_when_read_retries_are_enabled(
    settings: Settings,
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    settings.resilience.retry_read_timeouts = True
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})

    async def failed_body() -> AsyncIterator[bytes]:
        yield b"{"
        raise httpx.ReadTimeout("offline")

    poll = upstream.get(f"/status/{REQUEST_ID}").mock(
        return_value=httpx.Response(200, content=failed_body())
    )

    response = await hosted_gateway.client.post("/v1/chat/completions", json=CHAT)

    assert response.status_code == 504
    assert post.call_count == poll.call_count == 1


@pytest.mark.parametrize("model", NVIDIA_MODELS)
async def test_documented_payment_required_is_sanitized_and_not_retried(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    model: str,
) -> None:
    post = upstream.post("/chat/completions").respond(
        402,
        json={"detail": "You have reached your limit of credits."},
    )

    response = await hosted_gateway.client.post(
        "/v1/chat/completions",
        json={**CHAT, "model": f"nvidia/{model}"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_account_error"
    assert "credits" not in response.text
    assert post.call_count == 1


async def test_total_deadline_cancels_pending_poll_without_resubmission(
    settings: Settings,
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    settings.resilience.deadline_s = 0.1
    cancelled = asyncio.Event()
    poll_attempts = 0
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})

    async def blocked(request: httpx.Request) -> httpx.Response:
        nonlocal poll_attempts
        poll_attempts += 1
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    poll = upstream.get(f"/status/{REQUEST_ID}").mock(side_effect=blocked)

    response = await asyncio.wait_for(
        hosted_gateway.client.post("/v1/chat/completions", json=CHAT), 5
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    assert cancelled.is_set()
    assert post.call_count == poll_attempts == 1
    assert poll.call_count == 0  # respx records completed calls, not a cancelled handler.


async def test_client_disconnect_cancels_pending_poll_before_response_headers(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
    issued_test_key: str,
) -> None:
    poll_started, cancelled = asyncio.Event(), asyncio.Event()
    poll_attempts = 0
    post = upstream.post("/chat/completions").respond(202, headers={"NVCF-REQID": REQUEST_ID})

    async def blocked(request: httpx.Request) -> httpx.Response:
        nonlocal poll_attempts
        poll_attempts += 1
        poll_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    poll = upstream.get(f"/status/{REQUEST_ID}").mock(side_effect=blocked)
    received = False
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": json.dumps(CHAT).encode(), "more_body": False}
        await poll_started.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

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

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(hosted_gateway.app(scope, receive, send), 5)
    await asyncio.wait_for(hosted_gateway.recorded.wait(), 5)

    assert cancelled.is_set()
    assert post.call_count == poll_attempts == 1
    assert poll.call_count == 0
    assert not sent
    assert hosted_gateway.records[0].outcome == "client_disconnected"
