import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, STREAM, sse

pytestmark = pytest.mark.respx(assert_all_called=False)


@pytest.mark.parametrize("first_chunk", [False, True])
async def test_stream_deadline_ends_at_first_chunk(
    resilient: ResilientApp, first_chunk: bool
) -> None:
    closed = asyncio.Event()

    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            if first_chunk:
                yield sse(STREAM[0])[0]
            await asyncio.sleep(0.04)
            yield sse(STREAM[1], "[DONE]")[0]

        async def aclose(self) -> None:
            closed.set()

    resilient.service.settings.deadline_s = 0.02
    route = resilient.router.post("https://groq.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, stream=Slow())
    )

    response = await resilient.client.post(
        "/v1/chat/completions", json={**CHAT_REQUEST, "stream": True}
    )

    assert response.status_code == 200
    assert ("upstream_timeout" in response.text) is not first_chunk
    assert ("[DONE]" in response.text) is first_chunk
    assert route.call_count == 1
    assert closed.is_set()
