"""Organization, team and client-key HTTP endpoints."""

import uuid

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.admin.api.auth import context, service
from llm_gateway.admin.api.idempotency import creation
from llm_gateway.admin.api.models import KeyBody, NameBody
from llm_gateway.admin.request_filters import query_values
from llm_gateway.admin.service.key_inventory import KeyFilters, key_page
from llm_gateway.admin.service.team_inventory import team_page
from llm_gateway.errors import GatewayError
from llm_gateway.tenants.models import Organization

router = APIRouter()


def page(items: list[dict[str, object]], size: int) -> dict[str, object]:
    visible = items[:size]
    return {"data": visible, "next_cursor": str(visible[-1]["id"]) if len(items) > size else None}


@router.post("/orgs")
async def create_org(request: Request, body: NameBody) -> dict[str, object]:
    admin = service(request)
    admin.require_platform()

    async def perform(session: AsyncSession | None) -> dict[str, object]:
        org = await admin.create_org(body.name, session)
        return {"id": str(org.id), "name": org.name}

    return await creation(request, body.model_dump(), perform)


@router.get("/orgs")
async def list_orgs(
    request: Request, cursor: uuid.UUID | None = None, page_size: int = Query(50, ge=1, le=500)
) -> dict[str, object]:
    admin = service(request)
    rows = await admin.list_orgs(cursor, page_size + 1)
    async with context(request).sessions() as session:
        count_query = select(func.count()).select_from(Organization)
        if admin.organization_id is not None:
            count_query = count_query.where(Organization.id == admin.organization_id)
        total = await session.scalar(count_query)
    result = page(
        [
            {"id": str(row.id), "name": row.name, "created_at": row.created_at.isoformat()}
            for row in rows
        ],
        page_size,
    )

    result["total"] = total
    return result


@router.post("/orgs/{org}/teams")
async def create_team(request: Request, org: str, body: NameBody) -> dict[str, object]:
    admin = service(request)

    async def perform(session: AsyncSession | None) -> dict[str, object]:
        team = await admin.create_team(org, body.name, session)
        return {"id": str(team.id), "organization_id": str(team.organization_id), "name": team.name}

    return await creation(request, body.model_dump(), perform)


@router.get("/orgs/{org}/teams")
async def list_teams(
    request: Request,
    org: str,
    cursor: uuid.UUID | None = None,
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    rows = await service(request).list_teams(org, cursor, page_size + 1)
    organization = await service(request).authorize_org(org)
    return await team_page(context(request).sessions, organization.id, rows, page_size)


@router.post("/orgs/{org}/teams/{team}/keys")
async def create_key(request: Request, org: str, team: str, body: KeyBody) -> dict[str, object]:
    admin = service(request)

    async def perform(session: AsyncSession | None) -> dict[str, object]:
        key = await admin.create_key(org, team, body.name, body.expires_in_days, session)
        return {"key": key, "key_id": key.split("_")[1]}

    return await creation(request, body.model_dump(), perform)


@router.get("/orgs/{org}/keys")
async def list_keys(
    request: Request,
    org: str,
    team: str | None = None,
    cursor: uuid.UUID | None = None,
    page_size: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    organization = await service(request).authorize_org(org)
    filters = KeyFilters.model_validate(query_values(request))
    async with context(request).sessions() as session:
        return await key_page(session, organization.id, filters)


@router.post("/keys/{key_id}/revoke")
async def revoke_key(request: Request, key_id: str) -> dict[str, object]:
    if not await service(request).revoke_key(key_id):
        raise GatewayError(404, "Key not found.", type="invalid_request_error", code="not_found")
    return {"revoked": True}
