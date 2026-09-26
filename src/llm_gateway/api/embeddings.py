from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.context import annotate
from llm_gateway.gateway_state import get_state
from llm_gateway.schemas.embeddings import EmbeddingRequest

router = APIRouter()


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    state = get_state(request)

    embedding = parse_request(
        EmbeddingRequest, await read_json_body(request, state.settings.max_request_bytes)
    )
    annotate(model=embedding.model)

    adapter, model = state.providers.resolve(embedding.model)
    annotate(provider=adapter.name)
    result = await adapter.embed(embedding, model)
    record_usage(result.usage)
    return Response(result.model_dump_json(exclude_unset=True), media_type="application/json")
