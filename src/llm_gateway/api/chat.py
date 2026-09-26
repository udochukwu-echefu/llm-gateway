from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage, require_price
from llm_gateway.api.streaming import ProviderStreamingResponse
from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.usage.binding import bind, unbind
from llm_gateway.usage.record import UsageEvent

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    state = get_state(request)
    chat = parse_request(
        ChatCompletionRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=chat.model, stream=chat.stream)
    adapter, model = state.providers.resolve(chat.model)
    price = require_price(state, adapter.name, model, "chat")
    annotate(provider=adapter.name)
    event = UsageEvent(
        request.state.principal,
        request.state.gateway_request_id,
        price,
        state.catalog,
        "chat",
        chat.stream,
    )
    request.state.usage_event = event
    token = bind(event)
    try:
        if chat.stream:
            stream = await adapter.open_chat_stream(chat, model)
            return ProviderStreamingResponse(
                stream, event=event, include_usage=chat.client_wants_stream_usage
            )
        completion = await adapter.chat(chat, model)
    except GatewayError:
        event.outcome = "upstream_error"
        raise
    finally:
        unbind(token)
    event.usage = completion.usage
    record_usage(completion.usage)
    return Response(completion.model_dump_json(exclude_unset=True), media_type="application/json")
