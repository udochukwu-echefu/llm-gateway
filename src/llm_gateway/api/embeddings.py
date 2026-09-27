from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from llm_gateway.api.common import parse_request, read_json_body, record_usage, require_price
from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.schemas.embeddings import EmbeddingRequest
from llm_gateway.usage.binding import bind, unbind
from llm_gateway.usage.record import UsageEvent

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
    if not adapter.capabilities.supports_embeddings:
        raise GatewayError(
            400,
            f"Parameter 'embeddings' is unsupported by provider '{adapter.name}'.",
            code="unsupported_parameter",
            type="invalid_request_error",
        )
    requested_at = datetime.now(UTC)
    price = require_price(state, adapter.name, model, "embedding", requested_at)
    event = UsageEvent(
        request.state.principal,
        request.state.gateway_request_id,
        price,
        state.catalog,
        "embeddings",
        False,
        requested_at=requested_at,
    )
    request.state.usage_event = event
    token = bind(event)
    try:
        result = await adapter.embed(embedding, model)
    except GatewayError as exc:
        event.status_code = exc.status_code
        event.outcome = "upstream_error"
        raise
    finally:
        unbind(token)
    event.usage = result.usage
    record_usage(result.usage)
    return Response(result.model_dump_json(exclude_unset=True), media_type="application/json")
