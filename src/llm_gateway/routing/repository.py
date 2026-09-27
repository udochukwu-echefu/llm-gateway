"""Policy mutations and audit entries share one Postgres transaction."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event
from llm_gateway.catalog import Catalog
from llm_gateway.routing.policy import ModelPolicy, validate_patterns
from llm_gateway.tenants.models import Organization, Team


class PolicyRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], actor: str) -> None:
        self.sessions, self.actor = sessions, actor

    async def set_models(
        self, org: str, team: str | None, patterns: list[str] | None, catalog: Catalog
    ) -> None:
        validated = validate_patterns(patterns, catalog) if patterns is not None else None
        async with self.sessions.begin() as session:
            organization, member = await _owners(session, org, team)
            owner = member if member is not None else organization
            owner.model_patterns = list(validated) if validated is not None else None
            await append_event(
                session,
                self.actor,
                "clear-models" if patterns is None else "set-models",
                "team" if member is not None else "organization",
                str(owner.id),
                {"allow": ", ".join(validated)} if validated is not None else {},
            )

    async def get_models(self, org: str, team: str | None) -> ModelPolicy:
        async with self.sessions() as session:
            organization, member = await _owners(session, org, team)
            return ModelPolicy(
                tuple(organization.model_patterns)
                if organization.model_patterns is not None
                else None,
                tuple(member.model_patterns)
                if member is not None and member.model_patterns is not None
                else None,
            )


async def _owners(
    session: AsyncSession, org: str, team: str | None
) -> tuple[Organization, Team | None]:
    organization = await session.scalar(select(Organization).where(Organization.name == org))
    if organization is None:
        raise ValueError("Organization not found")
    if team is None:
        return organization, None
    member = await session.scalar(
        select(Team).where(Team.organization_id == organization.id, Team.name == team)
    )
    if member is None:
        raise ValueError("Team not found")
    return organization, member
