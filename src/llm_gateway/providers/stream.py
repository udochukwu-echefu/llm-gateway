from collections.abc import AsyncIterator, Callable

import httpx
from pydantic import ValidationError

from llm_gateway.errors import GatewayError
from llm_gateway.providers.transport import invalid_response, transport_error
from llm_gateway.schemas.chat import ChatCompletionChunk, StreamErrorEvent
from llm_gateway.sse import DONE, SSEDecoder


class CompatibleChatStream:
    """Decode and validate provider SSE without exposing bytes to the API layer."""

    def __init__(
        self, response: httpx.Response, normalize: Callable[[ChatCompletionChunk], None]
    ) -> None:
        self._response = response
        self._normalize = normalize

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]:
        return self._chunks()

    async def aclose(self) -> None:
        await self._response.aclose()

    async def _chunks(self) -> AsyncIterator[ChatCompletionChunk]:
        decoder = SSEDecoder()
        finished = False
        try:
            async for raw in self._response.aiter_bytes():
                for event in decoder.feed(raw):
                    if event.data == DONE:
                        return
                    chunk = _parse_chunk(event.data)
                    self._normalize(chunk)
                    finished = finished or any(c.finish_reason for c in chunk.choices)
                    yield chunk
        except httpx.HTTPError as exc:
            raise transport_error(exc) from exc
        if not finished:
            raise GatewayError(
                502,
                "The model provider ended the stream early.",
                type="upstream_error",
                code="upstream_stream_truncated",
            )


def _parse_chunk(data: str) -> ChatCompletionChunk:
    try:
        return ChatCompletionChunk.model_validate_json(data)
    except ValidationError as exc:
        try:
            StreamErrorEvent.model_validate_json(data)
        except ValidationError:
            raise invalid_response(exc) from None
        raise GatewayError(
            502,
            "The model provider reported an error during the stream.",
            type="upstream_error",
            code="upstream_stream_error",
        ) from None
