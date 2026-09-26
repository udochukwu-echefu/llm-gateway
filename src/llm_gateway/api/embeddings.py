from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage
from llm_gateway.config import Settings
from llm_gateway.context import annotate
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from llm_gateway.upstream import UpstreamClient, read_model

router = APIRouter()


@router.post("/v1/embeddings")
async def embeddings(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    upstream: UpstreamClient = request.app.state.upstream

    embedding = parse_request(
        EmbeddingRequest, await read_json_body(request, settings.max_request_bytes)
    )
    annotate(model=embedding.model)

    response = await upstream.open("embeddings", embedding.to_upstream(settings.upstream_provider))
    annotate(upstream_request_id=response.headers.get("x-request-id"))

    result = await read_model(response, EmbeddingResponse)
    record_usage(result.usage)
    return Response(result.model_dump_json(exclude_unset=True), media_type="application/json")
