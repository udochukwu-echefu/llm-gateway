from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.api.streaming import ProviderStreamingResponse
from llm_gateway.context import annotate
from llm_gateway.gateway_state import get_state
from llm_gateway.schemas.chat import ChatCompletionRequest

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    state = get_state(request)
    chat = parse_request(
        ChatCompletionRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=chat.model, stream=chat.stream)
    adapter, model = state.providers.resolve(chat.model)
    annotate(provider=adapter.name)

    if chat.stream:
        stream = await adapter.open_chat_stream(chat, model)
        return ProviderStreamingResponse(stream, include_usage=chat.client_wants_stream_usage)
    completion = await adapter.chat(chat, model)
    record_usage(completion.usage)
    return Response(completion.model_dump_json(exclude_unset=True), media_type="application/json")
