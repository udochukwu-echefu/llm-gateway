"""Persist non-secret creation metadata for bounded admin-tool retries."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.admin.api.auth import context
from llm_gateway.errors import GatewayError
from llm_gateway.tenants.models import AdminIdempotency


async def creation(
    request: Request,
    body: object,
    perform: Callable[[AsyncSession | None], Awaitable[dict[str, object]]],
) -> dict[str, object]:
    token = request.headers.get("idempotency-key")
    if token is None:
        return await perform(None)
    if not 1 <= len(token) <= 256:
        raise GatewayError(
            400,
            "Invalid Idempotency-Key.",
            type="invalid_request_error",
            code="invalid_idempotency_key",
        )
    ctx = context(request)
    actor = request.state.admin_principal.key_id
    route = request.url.path
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    body_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    address = f"{actor}:{route}:{token_hash}"
    lock = int.from_bytes(hashlib.sha256(address.encode()).digest()[:8], "big", signed=True)
    async with ctx.sessions.begin() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
        await session.execute(
            delete(AdminIdempotency).where(AdminIdempotency.expires_at <= datetime.now(UTC))
        )
        row = await session.scalar(
            select(AdminIdempotency).where(
                AdminIdempotency.actor == actor,
                AdminIdempotency.route == route,
                AdminIdempotency.token_hash == token_hash,
            )
        )
        if row is not None:
            if row.request_hash != body_hash:
                raise GatewayError(
                    409,
                    "Idempotency-Key used with a different request.",
                    type="invalid_request_error",
                    code="idempotency_conflict",
                )
            return dict(row.response)
        result = await perform(session)
        replay = {name: value for name, value in result.items() if name != "key"}
        if "key" in result:
            replay["secret_already_returned"] = True
        session.add(
            AdminIdempotency(
                actor=actor,
                route=route,
                token_hash=token_hash,
                request_hash=body_hash,
                response=replay,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        return result
