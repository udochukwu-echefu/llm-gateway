from functools import partial

from fastapi import APIRouter, Request, Response

from llm_gateway.api.caching import execute_with_cache
from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.api.disconnect import until_disconnected
from llm_gateway.api.execution import begin_execution
from llm_gateway.api.guardrails import begin_guardrails, guarded_call
from llm_gateway.api.streaming import ProviderStreamingResponse
from llm_gateway.context import annotate
from llm_gateway.gateway_state import get_state
from llm_gateway.guardrails.scheduling import inspect_large
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest
from llm_gateway.schemas.embeddings import EmbeddingResponse

router = APIRouter()


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    state = get_state(request)
    chat = parse_request(
        ChatCompletionRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=chat.model, stream=chat.stream)
    execution = await begin_execution(request, chat.model)
    chat = chat.model_copy(update={"model": execution.requested_model})
    guardrails = begin_guardrails(request)
    chat = await inspect_large(lambda: guardrails.protect_input(chat), chat)
    result, cache_result = await execute_with_cache(
        request,
        chat,
        execution,
        "chat",
        ChatCompletion,
        lambda: guarded_call(
            guardrails,
            lambda: until_disconnected(
                request, lambda: state.resilience.execute_chat(chat, execution)
            ),
            execution,
        ),
    )
    headers = {**execution.headers, "x-lgw-cache": cache_result}
    if isinstance(result, EmbeddingResponse):
        raise RuntimeError("chat returned an embedding")
    if not isinstance(result, ChatCompletion):
        response = ProviderStreamingResponse(
            result, event=execution.events[-1], include_usage=chat.client_wants_stream_usage
        )
        response.headers.update(headers)
        return response
    record_usage(result.usage)
    if cache_result == "hit":
        result = await inspect_large(partial(guardrails.protect_output, result), result)
    result = await inspect_large(partial(guardrails.restore_output, result), result)
    return Response(
        result.model_dump_json(exclude_unset=True),
        media_type="application/json",
        headers=headers,
    )
