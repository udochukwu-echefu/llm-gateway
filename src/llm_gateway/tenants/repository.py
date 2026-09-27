"""Persistent tenant records; HTTP authentication depends only on the small protocol."""

import getpass
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event
from llm_gateway.config import AdminSettings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.routing.policy import ModelPolicy
from llm_gateway.tenants.models import ApiKey, Organization, Team, TeamLimits, utc_now


@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    secret_hash: bytes
    organization_id: uuid.UUID
    team_id: uuid.UUID
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    limits: LimitOverrides = field(default_factory=LimitOverrides)
    policy: ModelPolicy = field(default_factory=ModelPolicy)


class KeyRepository(Protocol):
    async def get_key(self, key_id: str) -> KeyRecord | None: ...
    async def ping(self) -> None: ...


class PostgresKeyRepository:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], actor: str | None = None
    ) -> None:
        self.sessions = sessions
        self.actor = actor or AdminSettings().actor or f"{getpass.getuser()}@{socket.gethostname()}"

    async def ping(self) -> None:
        async with self.sessions() as session:
            await session.execute(text("SELECT 1"))

    async def get_key(self, key_id: str) -> KeyRecord | None:
        async with self.sessions() as session:
            result = await session.execute(
                select(
                    ApiKey,
                    Team.organization_id,
                    TeamLimits,
                    Organization.model_patterns,
                    Team.model_patterns,
                )
                .join(Team, ApiKey.team_id == Team.id)
                .join(Organization, Team.organization_id == Organization.id)
                .outerjoin(TeamLimits, TeamLimits.team_id == Team.id)
                .where(ApiKey.key_id == key_id)
            )
            row = result.one_or_none()
            if row is None:
                return None
            key, organization_id, raw_limits, org_patterns, team_patterns = row
            limits = cast(TeamLimits | None, raw_limits)
            override = (
                LimitOverrides()
                if limits is None
                else LimitOverrides(
                    limits.rpm,
                    limits.tpm,
                    limits.max_concurrency,
                    limits.monthly_budget_usd,
                    limits.alert_threshold,
                )
            )
            return KeyRecord(
                key.key_id,
                key.secret_hash,
                organization_id,
                key.team_id,
                key.expires_at,
                key.revoked_at,
                override,
                ModelPolicy(
                    tuple(org_patterns) if org_patterns is not None else None,
                    tuple(team_patterns) if team_patterns is not None else None,
                ),
            )

    async def create_org(self, name: str) -> Organization:
        async with self.sessions.begin() as session:
            org = Organization(name=name)
            session.add(org)
            await session.flush()
            await session.refresh(org)
            await append_event(session, self.actor, "create-org", "organization", str(org.id))
            return org

    async def create_team(self, org_name: str, name: str) -> Team:
        async with self.sessions.begin() as session:
            org = await session.scalar(select(Organization).where(Organization.name == org_name))
            if org is None:
                raise ValueError("Organization not found")
            team = Team(organization_id=org.id, name=name)
            session.add(team)
            await session.flush()
            await session.refresh(team)
            await append_event(session, self.actor, "create-team", "team", str(team.id))
            return team

    async def create_key(
        self,
        org_name: str,
        team_name: str,
        name: str,
        key_id: str,
        secret_hash: bytes,
        expires_at: datetime | None = None,
    ) -> None:
        async with self.sessions.begin() as session:
            team = await session.scalar(
                select(Team)
                .join(Organization)
                .where(Organization.name == org_name, Team.name == team_name)
            )
            if team is None:
                raise ValueError("Team not found")
            session.add(
                ApiKey(
                    team_id=team.id,
                    name=name,
                    key_id=key_id,
                    secret_hash=secret_hash,
                    expires_at=expires_at,
                )
            )

            await append_event(session, self.actor, "create-key", "key", key_id)

    async def list_keys(self, org_name: str, team_name: str | None = None) -> list[ApiKey]:
        async with self.sessions() as session:
            query = (
                select(ApiKey).join(Team).join(Organization).where(Organization.name == org_name)
            )
            if team_name is not None:
                query = query.where(Team.name == team_name)
            return list((await session.scalars(query.order_by(ApiKey.created_at))).all())

    async def revoke_key(self, key_id: str) -> bool:
        async with self.sessions.begin() as session:
            key = await session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))
            if key is None:
                return False
            if key.revoked_at is None:
                key.revoked_at = utc_now()
            await append_event(session, self.actor, "revoke-key", "key", key_id)
            return True

    async def team_limits(self, org_name: str, team_name: str) -> tuple[uuid.UUID, LimitOverrides]:
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(Team.id, TeamLimits)
                    .join(Organization)
                    .outerjoin(TeamLimits, TeamLimits.team_id == Team.id)
                    .where(Organization.name == org_name, Team.name == team_name)
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Team not found")
            team_id, raw_limits = row
            limits = cast(TeamLimits | None, raw_limits)
            return team_id, LimitOverrides(
                limits.rpm,
                limits.tpm,
                limits.max_concurrency,
                limits.monthly_budget_usd,
                limits.alert_threshold,
            ) if limits is not None else LimitOverrides()

    async def set_limits(
        self,
        org: str,
        team: str,
        *,
        rpm: int | None = None,
        tpm: int | None = None,
        max_concurrency: int | None = None,
        budget: Decimal | None = None,
        alert: Decimal | None = None,
        clear: bool = False,
    ) -> None:
        team_id, _ = await self.team_limits(org, team)
        async with self.sessions.begin() as session:
            if clear:
                await session.execute(delete(TeamLimits).where(TeamLimits.team_id == team_id))
                await append_event(session, self.actor, "clear-limits", "team", str(team_id))
                return
            row = await session.get(TeamLimits, team_id)
            if row is None:
                row = TeamLimits(team_id=team_id)
                session.add(row)
            for name, value in (
                ("rpm", rpm),
                ("tpm", tpm),
                ("max_concurrency", max_concurrency),
                ("monthly_budget_usd", budget),
                ("alert_threshold", alert),
            ):
                if value is not None:
                    setattr(row, name, value)

            details: dict[str, str | int | None] = {}
            for name, value in (
                ("rpm", rpm),
                ("tpm", tpm),
                ("max_concurrency", max_concurrency),
                ("monthly_budget_usd", budget),
                ("alert_threshold", alert),
            ):
                if value is not None:
                    details[name] = str(value) if isinstance(value, Decimal) else value
            action = "set-budget" if budget is not None else "set-limits"
            await append_event(session, self.actor, action, "team", str(team_id), details)
