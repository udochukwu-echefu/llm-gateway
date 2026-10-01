"""Metadata-only request list and complete attempt timeline."""

from fastapi import APIRouter, Request
from sqlalchemy import select

from llm_gateway.admin.api.auth import context, service
from llm_gateway.admin.request_filters import RequestFilters, query_values
from llm_gateway.admin.service.request_log import metadata, request_page
from llm_gateway.usage.repository import UsageRow

router = APIRouter()


@router.get("/orgs/{org}/requests")
async def requests(request: Request, org: str) -> dict[str, object]:
    organization = await service(request).authorize_org(org)
    filters = RequestFilters.model_validate(query_values(request))
    async with context(request).sessions() as session:
        return await request_page(session, organization.id, filters)


@router.get("/orgs/{org}/requests/{request_id}")
async def request_detail(request: Request, org: str, request_id: str) -> dict[str, object]:
    organization = await service(request).authorize_org(org)
    if request.query_params or len(request_id) > 128:
        raise ValueError("Invalid request detail query")
    async with context(request).sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(UsageRow)
                    .where(
                        UsageRow.organization_id == organization.id,
                        UsageRow.request_id == request_id,
                    )
                    .order_by(UsageRow.attempt, UsageRow.created_at, UsageRow.id)
                )
            ).all()
        )
    if not rows:
        raise ValueError("Request not found")
    return {"data": [metadata(row) for row in rows]}
