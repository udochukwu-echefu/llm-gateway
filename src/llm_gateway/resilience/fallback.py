"""Only the requested model's reviewed alternatives are eligible for this request."""

from dataclasses import dataclass
from datetime import datetime

from llm_gateway.catalog import Catalog, ModelPrice
from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import ProviderAdapter
from llm_gateway.providers.registry import ProviderRegistry
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.embeddings import EmbeddingRequest

ModelRequest = ChatCompletionRequest | EmbeddingRequest


@dataclass(frozen=True)
class Target:
    adapter: ProviderAdapter
    model: str
    price: ModelPrice


def resolve_target(
    name: str,
    request: ModelRequest,
    registry: ProviderRegistry,
    catalog: Catalog,
    requested_at: datetime,
) -> Target:
    adapter, model = registry.resolve(name)
    if isinstance(request, ChatCompletionRequest):
        adapter.validate_chat(request, model)
        kind = "chat"
    else:
        adapter.validate_embedding(request, model)
        kind = "embedding"
    price = catalog.find(adapter.name, model, kind)
    if price is None or price.at(requested_at) is None:
        raise GatewayError(
            404,
            f"Model '{name}' is not in this gateway's catalogue.",
            type="invalid_request_error",
            code="model_not_found",
        )
    return Target(adapter, model, price)


def unavailable() -> GatewayError:
    return GatewayError(
        503,
        "The model provider is temporarily unavailable.",
        type="upstream_error",
        code="provider_unavailable",
    )
