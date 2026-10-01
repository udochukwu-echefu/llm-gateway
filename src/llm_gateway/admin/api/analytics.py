"""Aggregate API is separate from billing-oriented usage summaries."""

from fastapi import APIRouter, Request

from llm_gateway.admin.api.auth import context, service
from llm_gateway.admin.request_filters import query_values
from llm_gateway.admin.service.analytics import AnalyticsFilters, analytics

router = APIRouter()


@router.get("/orgs/{org}/analytics")
async def get_analytics(request: Request, org: str) -> dict[str, object]:
    organization = await service(request).authorize_org(org)
    filters = AnalyticsFilters.model_validate(query_values(request))
    async with context(request).sessions() as session:
        return {
            "data": await analytics(session, organization.id, filters),
            "semantics": "recorded attempts; UTC buckets",
        }
