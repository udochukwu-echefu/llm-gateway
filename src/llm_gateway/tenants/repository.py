"""Persistent tenant records; HTTP authentication depends only on the small protocol."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.tenants.models import ApiKey, Organization, Team, utc_now


@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    secret_hash: bytes
    organization_id: uuid.UUID
    team_id: uuid.UUID
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class KeyRepository(Protocol):
    async def get_key(self, key_id: str) -> KeyRecord | None: ...
    async def ping(self) -> None: ...


class PostgresKeyRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def ping(self) -> None:
        async with self.sessions() as session:
            await session.execute(text("SELECT 1"))

    async def get_key(self, key_id: str) -> KeyRecord | None:
        async with self.sessions() as session:
            result = await session.execute(
                select(ApiKey, Team.organization_id)
                .join(Team, ApiKey.team_id == Team.id)
                .where(ApiKey.key_id == key_id)
            )
            row = result.one_or_none()
            if row is None:
                return None
            key, organization_id = row
            return KeyRecord(
                key.key_id,
                key.secret_hash,
                organization_id,
                key.team_id,
                key.expires_at,
                key.revoked_at,
            )

    async def create_org(self, name: str) -> Organization:
        async with self.sessions.begin() as session:
            org = Organization(name=name)
            session.add(org)
            await session.flush()
            await session.refresh(org)
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
            return True
