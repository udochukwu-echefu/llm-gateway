"""Validated policy changes and their audit event commit together."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event
from llm_gateway.guardrails.policy import GuardrailPolicy, parse_actions, parse_regions
from llm_gateway.routing.policy import ModelPolicy
from llm_gateway.tenants.models import Organization, Team


class GuardrailRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], actor: str) -> None:
        self.sessions, self.actor = sessions, actor

    async def set_policy(
        self, org: str, team: str | None, *, residency: bool, values: list[str] | None
    ) -> None:
        validated: list[str] | None
        if residency:
            regions = parse_regions(values)
            validated = list(regions) if regions is not None else None
        else:
            validated = (
                [f"{name}={action}" for name, action in parse_actions(values)]
                if values is not None
                else None
            )
        async with self.sessions.begin() as session:
            organization, member = await owners(session, org, team)
            owner = member if member is not None else organization
            if residency:
                owner.allowed_regions = validated
            else:
                owner.guardrail_actions = validated
            command = ("clear-" if values is None else "set-") + (
                "residency" if residency else "guardrails"
            )
            await append_event(
                session,
                self.actor,
                command,
                "team" if member is not None else "organization",
                str(owner.id),
                {"regions" if residency else "actions": ", ".join(validated)}
                if validated is not None
                else {},
            )

    async def get_policy(self, org: str, team: str | None) -> tuple[GuardrailPolicy, ModelPolicy]:
        async with self.sessions() as session:
            organization, member = await owners(session, org, team)
            return GuardrailPolicy(
                parse_actions(organization.guardrail_actions or []),
                parse_actions(member.guardrail_actions or []) if member is not None else (),
            ), ModelPolicy(
                tuple(organization.model_patterns)
                if organization.model_patterns is not None
                else None,
                tuple(member.model_patterns)
                if member is not None and member.model_patterns is not None
                else None,
                parse_regions(organization.allowed_regions),
                parse_regions(member.allowed_regions) if member is not None else None,
            )


async def owners(
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
