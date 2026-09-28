"""Persist creation results for bounded admin-tool retries.

The response is encrypted because creating a client key returns its secret once.
"""

import base64
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Request
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.admin_api.auth import context
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
    cipher = AESGCM(hashlib.sha256(b"admin-idempotency-v1:" + ctx.pepper).digest())
    async with ctx.sessions.begin() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
        row = await session.scalar(
            select(AdminIdempotency).where(
                AdminIdempotency.actor == actor,
                AdminIdempotency.route == route,
                AdminIdempotency.token_hash == token_hash,
            )
        )
        if row is not None and row.expires_at <= datetime.now(UTC):
            await session.execute(delete(AdminIdempotency).where(AdminIdempotency.id == row.id))
            row = None
        if row is not None:
            if row.request_hash != body_hash:
                raise GatewayError(
                    409,
                    "Idempotency-Key used with a different request.",
                    type="invalid_request_error",
                    code="idempotency_conflict",
                )
            sealed = base64.b64decode(str(row.response["sealed"]))
            return json.loads(cipher.decrypt(sealed[:12], sealed[12:], address.encode()))
        result = await perform(session)
        nonce = __import__("os").urandom(12)
        payload = json.dumps(result, default=str).encode()
        sealed = base64.b64encode(nonce + cipher.encrypt(nonce, payload, address.encode())).decode()
        session.add(
            AdminIdempotency(
                actor=actor,
                route=route,
                token_hash=token_hash,
                request_hash=body_hash,
                response={"sealed": sealed},
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        return result
