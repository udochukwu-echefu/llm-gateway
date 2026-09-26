from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.config import Settings
from llm_gateway.context import annotate
from llm_gateway.providers.registry import ProviderRegistry
from llm_gateway.schemas.embeddings import EmbeddingRequest

router = APIRouter()


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    registry: ProviderRegistry = request.app.state.providers

    embedding = parse_request(
        EmbeddingRequest, await read_json_body(request, settings.max_request_bytes)
    )
    annotate(model=embedding.model)

    adapter, model = registry.resolve(embedding.model)
    annotate(provider=adapter.name)
    result = await adapter.embed(embedding, model)
    record_usage(result.usage)
    return Response(result.model_dump_json(exclude_unset=True), media_type="application/json")
