"""Usage, cache invalidation and audit HTTP endpoints."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Request

from llm_gateway.admin_api.auth import context, service
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
                key: str(value)
                if key == "cost_usd" or key == "saved_usd" or isinstance(value, date)
                else value
                for key, value in row.items()
            }
            for row in visible
        ],
        "next_cursor": str(visible[-1]["group"]) if len(rows) > page_size else None,
    }


@router.post("/orgs/{org}/cache/purge")
async def purge_cache(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    client = context(request).redis
    if client is None:
        raise GatewayError(503, "Cache unavailable.", type="server_error", code="cache_unavailable")
    count = await service(request).purge_cache(org, team, client)
    return {"purged": count}


@router.get("/audit")
async def audit(
    request: Request,
    since: date | None = None,
    action: str | None = None,
    cursor: int | None = None,
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    events = await service(request).list_audit(since, action, cursor, page_size + 1)
    visible = events[:page_size]
    return {
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
