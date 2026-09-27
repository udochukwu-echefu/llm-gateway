"""Authenticate at the router boundary, before endpoints read request bodies."""

import asyncio
import ipaddress
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

import structlog
from fastapi import Request

from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.limits.configuration import resolve
from llm_gateway.observability.tracing import current, span
from llm_gateway.tenants.keys import hash_secret, parse_key, verify_hash
from llm_gateway.tenants.repository import KeyRecord

log = structlog.get_logger("llm_gateway.auth")


@dataclass(frozen=True)
class Principal:
    organization_id: uuid.UUID
    team_id: uuid.UUID
    key_id: str


async def authenticate(request: Request) -> None:
    with span("authenticate"):
        principal, record = await _credentials(request)
    with span("limits.admission"):
        await _admit(request, principal, record)


async def _credentials(request: Request) -> tuple[Principal, KeyRecord]:
    state = get_state(request)
    ip = client_ip(request, state.settings.trusted_proxy_hops)
    if state.limits is not None:
        await state.limits.ip_check(ip)
    header = request.headers.get("authorization", "")
    scheme, separator, token = header.partition(" ")
    parsed = parse_key(token) if separator and scheme.lower() == "bearer" else None
    if parsed is None:
        if state.limits is not None:
            await state.limits.ip_failure(ip)
        _reject("missing_or_malformed")
    key_id, secret = parsed
    record: KeyRecord | None = state.key_cache.get(key_id)
    verified_from_database = record is None
    if record is None:
        record = await state.key_repository.get_key(key_id)
    actual = hash_secret(state.pepper, secret)
    valid = verify_hash(record.secret_hash if record is not None else None, actual)
    if record is None:
        if state.limits is not None:
            await state.limits.ip_failure(ip)
        _reject("unknown_key_id")
    if not valid:
        if state.limits is not None:
            await state.limits.ip_failure(ip)
        _reject("wrong_secret")
    if record.revoked_at is not None:
        if state.limits is not None:
            await state.limits.ip_failure(ip)
        _reject("revoked")
    if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
        if state.limits is not None:
            await state.limits.ip_failure(ip)
        _reject("expired")
    if verified_from_database:
        state.key_cache.put(record)
    principal = Principal(record.organization_id, record.team_id, record.key_id)
    request.state.principal = principal
    return principal, record


async def _admit(request: Request, principal: Principal, record: KeyRecord) -> None:
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
    annotate(
        organization_id=str(principal.organization_id),
        team_id=str(principal.team_id),
        key_id=principal.key_id,
    )


def client_ip(request: Request, trusted_hops: int) -> str:
    if trusted_hops:
        forwarded = request.headers.get("x-forwarded-for", "")
        addresses = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(addresses) >= trusted_hops:
            try:
                return str(ipaddress.ip_address(addresses[-trusted_hops]))
            except ValueError:
                pass
    return request.client.host if request.client is not None else "unknown"


def _reject(reason: str) -> NoReturn:
    telemetry = current.get()
    if telemetry is not None:
        telemetry.metrics.auth_failures.labels(reason).inc()
    log.info("authentication_failed", reason=reason, key_id=None)
    raise GatewayError(
        401, "Invalid API key.", type="invalid_request_error", code="invalid_api_key"
    )
