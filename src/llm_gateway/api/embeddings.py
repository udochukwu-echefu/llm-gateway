from fastapi import APIRouter, Request, Response

from llm_gateway.api.caching import execute_with_cache
from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.api.execution import begin_execution
from llm_gateway.api.guardrails import begin_guardrails
from llm_gateway.context import annotate
from llm_gateway.gateway_state import get_state
from llm_gateway.guardrails.scheduling import inspect_large
from llm_gateway.observability.tracing import span
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse

router = APIRouter()


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    state = get_state(request)
    embedding = parse_request(
        EmbeddingRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=embedding.model)
    execution = await begin_execution(request, embedding.model)
    embedding = embedding.model_copy(update={"model": execution.requested_model})
    guardrails = begin_guardrails(request)
    embedding = await inspect_large(lambda: guardrails.protect_input(embedding), embedding)
    result, cache_result = await execute_with_cache(
        request,
        embedding,
        execution,
        "embeddings",
        EmbeddingResponse,
        lambda: state.resilience.execute_embedding(embedding, execution),
    )
    if not isinstance(result, EmbeddingResponse):
        raise RuntimeError("embedding returned a chat")
    record_usage(result.usage)
    with span("guardrails.output") as active:
        active.set_attribute("lgw.guardrails.text_fields", 0)
    return Response(
        result.model_dump_json(exclude_unset=True),
        media_type="application/json",
        headers={**execution.headers, "x-lgw-cache": cache_result},
    )
