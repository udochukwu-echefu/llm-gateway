"""The typed lifespan-owned resources shared by HTTP endpoints."""

from dataclasses import dataclass

from fastapi import FastAPI, Request

from llm_gateway.config import Settings
from llm_gateway.providers.registry import ProviderRegistry
from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.repository import KeyRepository


@dataclass(frozen=True)
class GatewayState:
    settings: Settings
    providers: ProviderRegistry
    key_repository: KeyRepository
    key_cache: VerifiedKeyCache
    pepper: bytes


def get_app_state(app: FastAPI) -> GatewayState:
    state = getattr(app.state, "gateway", None)
    if not isinstance(state, GatewayState):
        raise RuntimeError("Gateway lifespan has not started")
    return state


def get_state(request: Request) -> GatewayState:
    return get_app_state(request.app)
