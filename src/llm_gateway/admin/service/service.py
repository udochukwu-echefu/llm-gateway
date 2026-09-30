"""One administrative service for both entry points.

The repositories own transactions and append the matching audit event before commit.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy import String, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event, first_broken
from llm_gateway.audit.models import AuditEvent
from llm_gateway.cache.purge import purge
from llm_gateway.catalog import load_catalog
from llm_gateway.guardrails.policy import GuardrailPolicy
from llm_gateway.guardrails.repository import GuardrailRepository
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.routing.policy import ModelPolicy
from llm_gateway.routing.repository import PolicyRepository
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.models import AdminKey, ApiKey, Organization, Team, utc_now
from llm_gateway.tenants.repository import PostgresKeyRepository
from llm_gateway.usage.repository import PostgresUsageRepository


class AdminService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        pepper: bytes,
        actor: str,
        role: Literal["platform", "org"] = "platform",
        organization_id: uuid.UUID | None = None,
        usage_repository: PostgresUsageRepository | None = None,
    ) -> None:
        self.sessions = sessions
        self.pepper = pepper
        self.actor = actor
        self.role = role
        self.organization_id = organization_id
        self.usage_repository = usage_repository or PostgresUsageRepository(sessions)
        self.tenants = PostgresKeyRepository(sessions, actor)

    async def authorize_org(self, name: str) -> Organization:
        async with self.sessions() as session:
            org = await session.scalar(select(Organization).where(Organization.name == name))
        if org is None or (self.role == "org" and org.id != self.organization_id):
            raise ValueError("Organization not found")
        return org

    def require_platform(self) -> None:
        if self.role != "platform":
            raise PermissionError("Platform administrator required")

    async def create_admin_key(
        self, name: str, role: Literal["platform", "org"], org: str | None
    ) -> str:
        self.require_platform()
        organization_id = (await self.authorize_org(org)).id if org is not None else None
        if (role == "org") != (organization_id is not None):
            raise ValueError("Org keys require --org; platform keys cannot use --org")
        issued = issue_key(self.pepper, prefix="lgwa")
        async with self.sessions.begin() as session:
            session.add(
                AdminKey(
                    key_id=issued.key_id,
                    secret_hash=issued.secret_hash,
                    role=role,
                    organization_id=organization_id,
                    name=name,
                )
            )
            await append_event(session, self.actor, "create-admin-key", "admin-key", issued.key_id)
        return issued.full_key

    async def create_org(self, name: str, session: AsyncSession | None = None) -> Organization:
        self.require_platform()
        return await self.tenants.create_org(name, session)

    async def list_orgs(self, cursor: uuid.UUID | None, limit: int) -> list[Organization]:
        async with self.sessions() as session:
            query = select(Organization)
            if self.role == "org":
                query = query.where(Organization.id == self.organization_id)
            if cursor is not None:
                query = query.where(Organization.id > cursor)
            return list((await session.scalars(query.order_by(Organization.id).limit(limit))).all())

    async def create_team(self, org: str, name: str, session: AsyncSession | None = None) -> Team:
        if self.role == "org":
            await self.authorize_org(org)
        return await self.tenants.create_team(org, name, session)

    async def list_teams(self, org: str, cursor: uuid.UUID | None, limit: int) -> list[Team]:
        organization = await self.authorize_org(org)
        async with self.sessions() as session:
            query = select(Team).where(Team.organization_id == organization.id)
            if cursor is not None:
                query = query.where(Team.id > cursor)
            return list((await session.scalars(query.order_by(Team.id).limit(limit))).all())

    async def create_key(
        self,
        org: str,
        team: str,
        name: str,
        expires_in_days: int | None = None,
        session: AsyncSession | None = None,
    ) -> str:
        if self.role == "org":
            await self.authorize_org(org)
        if expires_in_days is not None and expires_in_days <= 0:
            raise ValueError("expires_in_days must be positive")
        expiry = datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days else None
        issued = issue_key(self.pepper)
        await self.tenants.create_key(
            org, team, name, issued.key_id, issued.secret_hash, expiry, session
        )
        return issued.full_key

    async def list_keys(
        self, org: str, team: str | None, cursor: uuid.UUID | None, limit: int | None
    ) -> list[ApiKey]:
        if limit is None:
            if self.role == "org":
                await self.authorize_org(org)
            return await self.tenants.list_keys(org, team)
        organization = await self.authorize_org(org)
        async with self.sessions() as session:
            query = select(ApiKey).join(Team).where(Team.organization_id == organization.id)
            if team is not None:
                query = query.where(Team.name == team)
            if cursor is not None:
                query = query.where(ApiKey.id > cursor)
            return list((await session.scalars(query.order_by(ApiKey.id).limit(limit))).all())

    async def revoke_key(self, key_id: str) -> bool:
        async with self.sessions() as session:
            owner = await session.scalar(
                select(Team.organization_id)
                .join(ApiKey, ApiKey.team_id == Team.id)
                .where(ApiKey.key_id == key_id)
            )
        if owner is not None:
            if self.role == "org" and owner != self.organization_id:
                return False
            return await self.tenants.revoke_key(key_id)
        return await self._revoke_admin_key(key_id)

    async def _revoke_admin_key(self, key_id: str) -> bool:
        async with self.sessions.begin() as session:
            key = await session.scalar(select(AdminKey).where(AdminKey.key_id == key_id))
            if key is None or (self.role == "org" and key.organization_id != self.organization_id):
                return False
            if key.revoked_at is None:
                key.revoked_at = utc_now()
            await append_event(session, self.actor, "revoke-admin-key", "admin-key", key_id)
            return True

    async def team_limits(self, org: str, team: str) -> tuple[uuid.UUID, LimitOverrides]:
        if self.role == "org":
            await self.authorize_org(org)
        return await self.tenants.team_limits(org, team)

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
        if self.role == "org":
            await self.authorize_org(org)
        await self.tenants.set_limits(
            org,
            team,
            rpm=rpm,
            tpm=tpm,
            max_concurrency=max_concurrency,
            budget=budget,
            alert=alert,
            clear=clear,
        )

    async def set_models(
        self,
        org: str,
        team: str | None,
        patterns: list[str] | None,
        expected_version: str | None = None,
    ) -> None:
        if self.role == "org":
            await self.authorize_org(org)
        await PolicyRepository(self.sessions, self.actor).set_models(
            org, team, patterns, load_catalog(), expected_version
        )

    async def policies(self, org: str, team: str | None) -> tuple[GuardrailPolicy, ModelPolicy]:
        await self.authorize_org(org)
        return await GuardrailRepository(self.sessions, self.actor).get_policy(org, team)

    async def policy_snapshot(
        self, org: str, team: str | None
    ) -> tuple[GuardrailPolicy, ModelPolicy, dict[str, str]]:
        await self.authorize_org(org)
        return await GuardrailRepository(self.sessions, self.actor).snapshot(org, team)

    async def set_policy(
        self,
        org: str,
        team: str | None,
        *,
        residency: bool,
        values: list[str] | None,
        expected_version: str | None = None,
    ) -> None:
        if self.role == "org":
            await self.authorize_org(org)
        await GuardrailRepository(self.sessions, self.actor).set_policy(
            org, team, residency=residency, values=values, expected_version=expected_version
        )

    async def usage(
        self,
        org: str,
        team: str | None,
        since: date | None,
        until: date | None,
        group_by: Literal["team", "key", "model", "day"],
    ) -> list[dict[str, Any]]:
        await self.authorize_org(org)
        if since is not None and until is not None and since > until:
            raise ValueError("since must be on or before until")
        return await self.usage_repository.report(org, team, since, until, group_by)

    async def purge_cache(self, org: str, team: str | None, client: Redis) -> int:
        if self.role == "org":
            await self.authorize_org(org)
        return await purge(self.tenants, client, org, team)

    async def list_audit(
        self, since: date | None, action: str | None, cursor: int | None, limit: int
    ) -> list[AuditEvent]:
        async with self.sessions() as session:
            query = select(AuditEvent)
            if self.role == "org":
                key_ids = (
                    select(ApiKey.key_id)
                    .join(Team)
                    .where(Team.organization_id == self.organization_id)
                )
                query = query.where(
                    or_(
                        (AuditEvent.target_type == "organization")
                        & (AuditEvent.target_id == str(self.organization_id)),
                        (AuditEvent.target_type == "team")
                        & AuditEvent.target_id.in_(
                            select(Team.id.cast(String)).where(
                                Team.organization_id == self.organization_id
                            )
                        ),
                        (AuditEvent.target_type == "key") & AuditEvent.target_id.in_(key_ids),
                    )
                )
            if since is not None:
                query = query.where(
                    AuditEvent.occurred_at >= datetime.combine(since, datetime.min.time(), UTC)
                )
            if action is not None:
                query = query.where(AuditEvent.action == action)
            if cursor is not None:
                query = query.where(AuditEvent.id > cursor)
            return list((await session.scalars(query.order_by(AuditEvent.id).limit(limit))).all())

    async def verify_audit(self) -> tuple[int, int | None]:
        self.require_platform()
        async with self.sessions() as session:
            events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
        return len(events), first_broken(events)
