"""Policy mutations and audit entries share one Postgres transaction."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event
from llm_gateway.catalog import Catalog
from llm_gateway.guardrails.repository import GuardrailRepository, owners
from llm_gateway.routing.policy import ModelPolicy, validate_patterns


class PolicyRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], actor: str) -> None:
        self.sessions, self.actor = sessions, actor

    async def set_models(
        self, org: str, team: str | None, patterns: list[str] | None, catalog: Catalog
    ) -> None:
        validated = validate_patterns(patterns, catalog) if patterns is not None else None
        async with self.sessions.begin() as session:
            organization, member = await owners(session, org, team)
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
        _, policy = await GuardrailRepository(self.sessions, self.actor).get_policy(org, team)
        return policy
