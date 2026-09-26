import json
from collections.abc import AsyncIterator

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from llm_gateway.api.common import record_usage
from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import ChatStream
from llm_gateway.sse import DONE, encode_data, encode_error


class ProviderStreamingResponse(StreamingResponse):
    """The API owns the stream and releases it even when ASGI cancels on disconnect."""

    def __init__(self, stream: ChatStream, *, include_usage: bool) -> None:
        self._stream = stream
        super().__init__(
            relay_chat_stream(stream, include_usage=include_usage),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._stream.aclose()


async def relay_chat_stream(stream: ChatStream, *, include_usage: bool) -> AsyncIterator[bytes]:
    try:
        async for chunk in stream:
            record_usage(chunk.usage)
            data = chunk.model_dump(mode="json", exclude_unset=True)
            if not include_usage and "usage" in data:
                if not chunk.choices:
                    continue
                del data["usage"]
            yield encode_data(json.dumps(data))
    except GatewayError as exc:
        yield encode_error(exc)
        return
    yield encode_data(DONE)
