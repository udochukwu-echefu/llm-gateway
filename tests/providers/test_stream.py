from collections.abc import AsyncIterator

import anyio
import httpx
import pytest
import respx
from starlette.types import Message

from llm_gateway.api.streaming import ProviderStreamingResponse
from llm_gateway.providers.openai_compat import OpenAICompatibleAdapter
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.fixtures import STREAM, parse_events, sse


class StalledStream(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield sse(STREAM[0])[0]
        await anyio.sleep_forever()

    async def aclose(self) -> None:
        self.closed = True


async def test_disconnect_closes_each_provider_stream(
    adapter: OpenAICompatibleAdapter,
    upstream: respx.MockRouter,
) -> None:
    stalled = StalledStream()
    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, stream=stalled))
    request = ChatCompletionRequest.model_validate(
        {
            "model": "model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
    )
    stream = await adapter.open_chat_stream(request, "model")
    response = ProviderStreamingResponse(stream, include_usage=False)
    first_chunk = anyio.Event()

    async def receive() -> Message:
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            first_chunk.set()

    with anyio.fail_after(2):
        await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)

    assert first_chunk.is_set()
    assert stalled.closed


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.ReadTimeout, "upstream_timeout"),
        (httpx.ReadError, "upstream_unavailable"),
    ],
)
async def test_interrupted_stream_is_a_final_error_and_closes(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    failure: type[httpx.HTTPError],
    code: str,
) -> None:
    class BrokenStream(StalledStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield sse(STREAM[0])[0]
            raise failure("private provider detail")

    broken = BrokenStream()
    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, stream=broken))

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    events = parse_events(response.text)
    assert response.status_code == 200
    assert len(events) == 2
    assert events[-1]["error"]["code"] == code
    assert "private provider detail" not in response.text
    assert broken.closed


@pytest.mark.parametrize(
    ("tail", "code"),
    [
        (b"data: \xff\n\n", "upstream_invalid_response"),
        (b'data: {"error":{"message":"private"}}\n\n', "upstream_stream_error"),
        (b"data: broken\n\n", "upstream_invalid_response"),
        (b"", "upstream_stream_truncated"),
    ],
)
async def test_invalid_stream_contract(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
    tail: bytes,
    code: str,
) -> None:
    async def wire() -> AsyncIterator[bytes]:
        yield sse(STREAM[0])[0]
        yield tail

    upstream.post("/chat/completions").mock(return_value=httpx.Response(200, content=wire()))

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )

    assert parse_events(response.text)[-1]["error"]["code"] == code


async def test_null_stream_options_still_requests_usage(
    client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    provider_name: ProviderName,
) -> None:
    upstream.post("/chat/completions").respond(200, content=b"".join(sse(*STREAM, "[DONE]")))

    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": f"{provider_name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
            "stream_options": None,
        },
    )

    assert response.status_code == 200
    assert parse_events(response.text)[-1] == "[DONE]"
