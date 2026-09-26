import json
from collections.abc import AsyncIterator
from functools import partial

import structlog
from fastapi import APIRouter, Request, Response
from pydantic import ValidationError

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.config import Settings
from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.schemas.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionRequest,
    StreamErrorEvent,
)
from llm_gateway.sse import DONE, SSEDecoder, encode_data, encode_error
from llm_gateway.upstream import (
    UpstreamClient,
    UpstreamStreamingResponse,
    invalid_response,
    read_model,
)

router = APIRouter()
log = structlog.get_logger("llm_gateway.chat")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    upstream: UpstreamClient = request.app.state.upstream

    chat = parse_request(
        ChatCompletionRequest, await read_json_body(request, settings.max_request_bytes)
    )
    annotate(model=chat.model, stream=chat.stream)

    response = await upstream.open("chat/completions", chat.to_upstream(settings.upstream_provider))
    # The provider's own ID for this call, for correlating with them when something breaks.
    annotate(upstream_request_id=response.headers.get("x-request-id"))

    if chat.stream:
        relay = partial(relay_chat_stream, include_usage=chat.client_wants_stream_usage)
        return UpstreamStreamingResponse(response, relay)

    completion = await read_model(response, ChatCompletion)
    record_usage(completion.usage)
    return Response(completion.model_dump_json(exclude_unset=True), media_type="application/json")


async def relay_chat_stream(
    upstream: AsyncIterator[bytes], *, include_usage: bool
) -> AsyncIterator[bytes]:
    """Check each streamed chunk against the canonical format and pass it on.

    Also records token usage, hides the usage chunk if the client didn't ask for it, and
    makes sure the stream always ends in a way the client can recognise.
    """
    decoder = SSEDecoder()
    finished = False  # the provider said why it stopped (finish_reason)

    async for raw in upstream:
        for event in decoder.feed(raw):
            if event.data == DONE:
                yield encode_data(DONE)
                return

            try:
                chunk = ChatCompletionChunk.model_validate_json(event.data)
            except ValidationError as exc:
                yield encode_error(_stream_failure(event.data, exc))
                return

            record_usage(chunk.usage)
            finished = finished or any(choice.finish_reason for choice in chunk.choices)
            data = chunk.model_dump(mode="json", exclude_unset=True)
            if not include_usage and "usage" in data:
                if not chunk.choices:
                    continue  # a usage-only chunk the client didn't ask for
                del data["usage"]
            yield encode_data(json.dumps(data))

    if finished:
        # Complete but without the [DONE] marker. Add it, so clients stop reading cleanly.
        log.warning("upstream_stream_missing_done")
        yield encode_data(DONE)
    else:
        log.warning("upstream_stream_truncated")
        yield encode_error(
            GatewayError(
                502,
                "The model provider ended the stream early.",
                type="upstream_error",
                code="upstream_stream_truncated",
            )
        )


def _stream_failure(data: str, exc: ValidationError) -> GatewayError:
    try:
        StreamErrorEvent.model_validate_json(data)
    except ValidationError:
        return invalid_response(exc)
    # The provider reported its own failure mid-stream. Same policy as a 5xx: generic
    # message to the client, details only in our logs.
    log.warning("upstream_stream_error")
    return GatewayError(
        502,
        "The model provider reported an error during the stream.",
        type="upstream_error",
        code="upstream_stream_error",
    )
