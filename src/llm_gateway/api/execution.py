"""Attach the attempt list before execution, including failing and cancelled calls."""

from fastapi import Request

from llm_gateway.resilience.execution import Execution


def begin_execution(request: Request, model: str) -> Execution:
    execution = Execution(
        request.state.principal,
        request.state.gateway_request_id,
        model,
        allow_fallback=request.headers.get("x-lgw-fallback", "").lower() != "disabled",
    )
    request.state.usage_events = execution.events
    return execution
