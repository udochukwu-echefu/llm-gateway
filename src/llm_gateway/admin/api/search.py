"""Global navigation search is scoped in SQL, before limiting results."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, or_, select

from llm_gateway.admin.api.auth import service
from llm_gateway.admin.request_filters import query_values
from llm_gateway.tenants.models import ApiKey, Organization, Team

router = APIRouter()


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=128)


@router.get("/search")
async def search(request: Request) -> dict[str, object]:
    query = SearchQuery.model_validate(query_values(request))
    admin = service(request)
    pattern = "%" + query.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    scope = [] if admin.role == "platform" else [Organization.id == admin.organization_id]
    results: list[dict[str, object]] = []
    async with admin.sessions() as session:
        orgs = (
            await session.scalars(
                select(Organization)
                .where(
                    *scope,
                    or_(
                        Organization.name.ilike(pattern, escape="\\"),
                        Organization.id.cast(String).ilike(pattern, escape="\\"),
                    ),
                )
                .order_by(Organization.name)
                .limit(30)
            )
        ).all()
        results.extend(
            {"kind": "org", "id": str(org.id), "name": org.name, "org": org.name} for org in orgs
        )
        teams = (
            await session.execute(
                select(Team, Organization.name)
                .join(Organization)
                .where(
                    *scope,
                    or_(
                        Team.name.ilike(pattern, escape="\\"),
                        Team.id.cast(String).ilike(pattern, escape="\\"),
                    ),
                )
                .order_by(Team.name)
                .limit(30)
            )
        ).all()
        results.extend(
            {"kind": "team", "id": str(team.id), "name": team.name, "org": org, "team": team.name}
            for team, org in teams
        )
        keys = (
            await session.execute(
                select(ApiKey, Team.name, Organization.name)
                .select_from(ApiKey)
                .join(Team, Team.id == ApiKey.team_id)
                .join(Organization, Organization.id == Team.organization_id)
                .where(
                    *scope,
                    or_(
                        ApiKey.name.ilike(pattern, escape="\\"),
                        ApiKey.key_id.ilike(pattern, escape="\\"),
                    ),
                )
                .order_by(ApiKey.name)
                .limit(30)
            )
        ).all()
        results.extend(
            {"kind": "key", "id": key.key_id, "name": key.name, "org": org, "team": team}
            for key, team, org in keys
        )
    return {"data": results[:30]}
