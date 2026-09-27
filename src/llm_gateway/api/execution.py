"""Resolve and authorize the destination before spending any admission capacity."""

from datetime import UTC, datetime

from fastapi import Request

from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.resilience.execution import Execution
from llm_gateway.routing.selection import available_models, resolve_model
from llm_gateway.tenants.admission import admit
from llm_gateway.tenants.auth import Principal


async def begin_execution(request: Request, model: str) -> Execution:
    state = get_state(request)
    principal: Principal = request.state.principal
    now = datetime.now(UTC)
    concrete, alias = resolve_model(
        model,
        state.catalog,
        principal.policy,
        available_models(state.catalog, state.providers.adapters, now),
        state.resilience.routing_random,
    )
    execution = Execution(
        principal,
        request.state.gateway_request_id,
        concrete,
        allow_fallback=request.headers.get("x-lgw-fallback", "").lower() != "disabled",
        requested_at=now,
        alias=alias,
    )
    request.state.usage_events = execution.events
    try:
        await admit(request)
    except GatewayError as exc:
        exc.headers.update(execution.headers)
        raise
    return execution
