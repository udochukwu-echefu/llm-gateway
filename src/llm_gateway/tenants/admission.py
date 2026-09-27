"""Budget and rate admission runs only after destination authorization."""

import asyncio

from fastapi import Request

from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.limits.configuration import resolve
from llm_gateway.observability.tracing import span
from llm_gateway.tenants.auth import Principal
from llm_gateway.tenants.repository import KeyRecord


async def admit(request: Request) -> None:
    with span("limits.admission"):
        await _admit(request)


async def _admit(request: Request) -> None:
    principal: Principal = request.state.principal
    record: KeyRecord = request.state.key_record
    state = get_state(request)
    if state.limits is not None:
        limits = resolve(record.limits, state.settings.limits)
        try:
            lease, headers = await state.limits.admission(principal.team_id, limits)
        except GatewayError as exc:
            for kind, limit in (("requests", limits.rpm), ("tokens", limits.tpm)):
                for field, value in (
                    ("limit", str(limit)),
                    ("remaining", "unavailable"),
                    ("reset", "unavailable"),
                ):
                    exc.headers.setdefault(f"x-ratelimit-{field}-{kind}", value)
            raise
        request.state.limit_admission = (principal.team_id, lease, limits)
        request.state.limit_headers = headers
        if lease is not None:
            request.state.limit_heartbeat = asyncio.create_task(
                state.limits.keep_lease_alive(principal.team_id, lease)
            )
