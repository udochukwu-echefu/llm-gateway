from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.api.execution import begin_execution
from llm_gateway.api.streaming import ProviderStreamingResponse
from llm_gateway.context import annotate
from llm_gateway.gateway_state import get_state
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    state = get_state(request)
    chat = parse_request(
        ChatCompletionRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=chat.model, stream=chat.stream)
    execution = begin_execution(request, chat.model)
    result = await state.resilience.execute_chat(chat, execution)
    if not isinstance(result, ChatCompletion):
        response = ProviderStreamingResponse(
            result, event=execution.events[-1], include_usage=chat.client_wants_stream_usage
        )
        response.headers.update(execution.headers)
        return response
    record_usage(result.usage)
    return Response(
        result.model_dump_json(exclude_unset=True),
        media_type="application/json",
        headers=execution.headers,
    )
