"""Offline, audited cache invalidation by verified team UUIDs."""

from collections.abc import AsyncIterator
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import select

from llm_gateway.audit.chain import append_event
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.tenants.repository import PostgresKeyRepository


async def purge(
    repository: PostgresKeyRepository, client: Redis, org_name: str, team_name: str | None
) -> int:
    async with repository.sessions.begin() as session:
        org = await session.scalar(select(Organization).where(Organization.name == org_name))
        if org is None:
            raise ValueError("Organization not found")
        query = select(Team.id).where(Team.organization_id == org.id)
        if team_name is not None:
            query = query.where(Team.name == team_name)
        teams = list((await session.scalars(query)).all())
        if team_name is not None and not teams:
            raise ValueError("Team not found")
        count = 0
        for team_id in teams:
            batch: list[bytes] = []
            keys = cast(
                AsyncIterator[bytes],
                client.scan_iter(match=f"lgw:cache:{team_id}:*"),  # pyright: ignore[reportUnknownMemberType]  # redis-py scan_iter returns Unknown
            )
            async for key in keys:
                batch.append(key)
                if len(batch) >= 100:
                    count += await client.unlink(*batch)
                    batch.clear()
            if batch:
                count += await client.unlink(*batch)
        await append_event(
            session,
            repository.actor,
            "cache-purge",
            "team" if team_name else "organization",
            str(teams[0]) if team_name else str(org.id),
        )
        return count
