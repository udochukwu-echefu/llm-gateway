"""Authenticate private admin keys independently of tenant credentials."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, NoReturn, cast

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.admin.service.service import AdminService
from llm_gateway.config import Settings
from llm_gateway.errors import GatewayError
from llm_gateway.limits.service import LimitService
from llm_gateway.tenants.auth import client_ip
from llm_gateway.tenants.keys import hash_secret, parse_key, verify_hash
from llm_gateway.tenants.models import AdminKey


@dataclass(frozen=True)
class AdminContext:
    sessions: async_sessionmaker[AsyncSession]
    pepper: bytes
    limits: LimitService | None
    redis: Redis | None
    trusted_proxy_hops: int = 0
    settings: Settings | None = None
    breaker_states: Callable[[], dict[str, str]] = field(default=lambda: {})


@dataclass(frozen=True)
class AdminPrincipal:
    key_id: str
    role: Literal["platform", "org", "viewer"]
    organization_id: uuid.UUID | None
    name: str


def context(request: Request) -> AdminContext:
    return cast(AdminContext, request.app.state.admin_context)


async def authenticate(request: Request) -> None:
    ctx = context(request)
    ip = client_ip(request, ctx.trusted_proxy_hops)
    scheme, separator, token = request.headers.get("authorization", "").partition(" ")
    parsed = parse_key(token, prefix="lgwa") if separator and scheme.lower() == "bearer" else None
    if parsed is None:
        await _reject(ctx.limits, ip)
    key_id, secret = parsed
    async with ctx.sessions() as session:
        record = await session.scalar(select(AdminKey).where(AdminKey.key_id == key_id))
    valid = verify_hash(
        record.secret_hash if record is not None else None, hash_secret(ctx.pepper, secret)
    )
    if (
        record is None
        or not valid
        or record.revoked_at is not None
        or (record.expires_at is not None and record.expires_at <= datetime.now(UTC))
    ):
        await _reject(ctx.limits, ip)
    request.state.admin_principal = AdminPrincipal(
        record.key_id,
        cast(Literal["platform", "org", "viewer"], record.role),
        record.organization_id,
        record.name,
    )
    if record.role == "viewer" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        raise GatewayError(
            403,
            "Read-only administrators cannot make changes.",
            type="invalid_request_error",
            code="read_only_admin",
        )


def service(request: Request) -> AdminService:
    ctx = context(request)
    principal = cast(AdminPrincipal, request.state.admin_principal)
    return AdminService(
        ctx.sessions,
        ctx.pepper,
        f"admin:{principal.key_id}",
        principal.role,
        principal.organization_id,
    )


async def _failure_limit(limits: LimitService, ip: str, increment: bool) -> None:
    result = await limits.safe(
        lambda: limits.window(ip, "admin-auth-fail", limits.ip_limit, int(increment), increment)
    )
    if isinstance(result, list) and not result[0]:
        raise GatewayError(
            429,
            "Too many authentication failures.",
            type="rate_limit_error",
            code="rate_limit_exceeded",
        )


async def _reject(limits: LimitService | None, ip: str) -> NoReturn:
    if limits is not None:
        await _failure_limit(limits, ip, True)
    raise GatewayError(
        401, "Invalid admin API key.", type="invalid_request_error", code="invalid_admin_key"
    )
