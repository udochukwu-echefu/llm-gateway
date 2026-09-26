"""Authenticate at the router boundary, before endpoints read request bodies."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

import structlog
from fastapi import Request

from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.tenants.keys import hash_secret, parse_key, verify_hash

log = structlog.get_logger("llm_gateway.auth")


@dataclass(frozen=True)
class Principal:
    organization_id: uuid.UUID
    team_id: uuid.UUID
    key_id: str


async def authenticate(request: Request) -> None:
    header = request.headers.get("authorization", "")
    scheme, separator, token = header.partition(" ")
    parsed = parse_key(token) if separator and scheme.lower() == "bearer" else None
    if parsed is None:
        _reject("missing_or_malformed")
    key_id, secret = parsed
    cache = request.app.state.key_cache
    repository = request.app.state.key_repository
    record = cache.get(key_id)
    if record is None:
        record = await repository.get_key(key_id)
    actual = hash_secret(request.app.state.pepper, secret)
    if not verify_hash(record.secret_hash if record else None, actual):
        _reject("unknown_or_wrong_secret")
    if record.revoked_at is not None:
        _reject("revoked")
    if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
        _reject("expired")
    cache.put(record)
    principal = Principal(record.organization_id, record.team_id, record.key_id)
    request.state.principal = principal
    annotate(
        organization_id=str(principal.organization_id),
        team_id=str(principal.team_id),
        key_id=principal.key_id,
    )


def _reject(reason: str) -> NoReturn:
    log.info("authentication_failed", reason=reason, key_id=None)
    raise GatewayError(
        401, "Invalid API key.", type="invalid_request_error", code="invalid_api_key"
    )
