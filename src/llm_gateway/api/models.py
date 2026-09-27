"""List configured, reviewed model IDs; auth is enforced by the v1 router."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from llm_gateway.gateway_state import get_state
from llm_gateway.routing.selection import available_models, visible_aliases
from llm_gateway.tenants.admission import admit
from llm_gateway.tenants.auth import Principal

router = APIRouter()


@router.get("/models")
async def list_models(request: Request) -> dict[str, object]:
    await admit(request)
    state = get_state(request)
    principal: Principal = request.state.principal
    configured = state.providers.adapters
    now = datetime.now(UTC)
    available = available_models(state.catalog, configured, now)
    aliases = visible_aliases(state.catalog, principal.policy, available)
    return {
        "object": "list",
        "data": [
            {"id": f"{entry.provider}/{entry.model}", "object": "model", "owned_by": entry.provider}
            for entry in state.catalog.models
            if f"{entry.provider}/{entry.model}" in available
            and principal.policy.allows(f"{entry.provider}/{entry.model}")
        ]
        + [{"id": name, "object": "model", "owned_by": "gateway"} for name in aliases],
    }
