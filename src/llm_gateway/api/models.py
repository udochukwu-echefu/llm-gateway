"""List configured, reviewed model IDs; auth is enforced by the v1 router."""

from fastapi import APIRouter, Request

from llm_gateway.gateway_state import get_state

router = APIRouter()


@router.get("/models")
async def list_models(request: Request) -> dict[str, object]:
    state = get_state(request)
    configured = state.providers.adapters
    return {
        "object": "list",
        "data": [
            {"id": f"{entry.provider}/{entry.model}", "object": "model", "owned_by": entry.provider}
            for entry in state.catalog.models
            if entry.provider in configured
        ],
    }
