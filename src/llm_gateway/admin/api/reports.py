"""Usage, cache invalidation and audit HTTP endpoints."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query, Request
from redis.exceptions import RedisError

from llm_gateway.admin.api.auth import context, service
from llm_gateway.errors import GatewayError

router = APIRouter()


@router.get("/orgs/{org}/usage")
async def usage(
    request: Request,
    org: str,
    since: date | None = None,
    until: date | None = None,
    group_by: Literal["team", "key", "model", "day"] = "team",
    cursor: str | None = None,
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    rows = await service(request).usage(org, None, since, until, group_by)
    if cursor is not None:
        rows = [row for row in rows if str(row["group"]) > cursor]
    visible = rows[:page_size]
    return {
        "data": [
            {
                key: format(value, "f")
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, date)
                else value
                for key, value in row.items()
            }
            for row in visible
        ],
        "next_cursor": str(visible[-1]["group"]) if len(rows) > page_size else None,
    }


@router.post("/orgs/{org}/cache/purge")
async def purge_cache(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    admin = service(request)
    await admin.authorize_org(org)
    client = context(request).redis
    if client is None:
        raise GatewayError(503, "Cache unavailable.", type="server_error", code="cache_unavailable")
    try:
        count = await admin.purge_cache(org, team, client)
    except (RedisError, TimeoutError) as exc:
        raise GatewayError(
            503, "Cache unavailable.", type="server_error", code="cache_unavailable"
        ) from exc
    return {"purged": count}


@router.get("/audit")
async def audit(
    request: Request,
    since: date | None = None,
    action: str | None = None,
    until: date | None = None,
    actor: str | None = None,
    target_type: str | None = None,
    cursor: int | None = None,
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    if set(request.query_params) - {
        "since",
        "until",
        "actor",
        "target_type",
        "action",
        "cursor",
        "page_size",
    }:
        raise ValueError("Unknown audit filter")
    if since is not None and until is not None and since > until:
        raise ValueError("since must be before until")
    events = await service(request).list_audit(
        since, action, cursor, page_size + 1, until, actor, target_type
    )
    visible = events[:page_size]
    total = await service(request).audit_count(since, until, action, actor, target_type)
    return {
        "total": total,
        "data": [
            {
                "id": event.id,
                "occurred_at": event.occurred_at.isoformat(),
                "actor": event.actor,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "details": event.details,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            }
            for event in visible
        ],
        "next_cursor": visible[-1].id if len(events) > page_size else None,
    }


@router.get("/audit/verify")
async def verify_audit(request: Request) -> dict[str, object]:
    count, broken = await service(request).verify_audit()
    return {"events": count, "valid": broken is None, "first_broken_id": broken}
