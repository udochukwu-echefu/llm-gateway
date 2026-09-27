"""Batch inserts and SQL aggregation; prices are captured at request time, not joined."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from llm_gateway.tenants.models import Base
from llm_gateway.usage.record import UsageRecord


class UsageRow(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"))
    key_id: Mapped[str] = mapped_column(String(12))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(256))
    endpoint: Mapped[str] = mapped_column(String(16))
    stream: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))
    cost_status: Mapped[str] = mapped_column(String(32))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 12))
    catalog_version: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    ttfb_ms: Mapped[float | None] = mapped_column(Float)


class PostgresUsageRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def month_spend(self, team_id: uuid.UUID, start: datetime, end: datetime) -> Decimal:
        async with self.sessions() as session:
            value = await session.scalar(
                select(func.sum(UsageRow.cost_usd)).where(
                    UsageRow.team_id == team_id,
                    UsageRow.created_at >= start,
                    UsageRow.created_at < end,
                )
            )
            return value if value is not None else Decimal(0)

    async def insert(self, records: Sequence[UsageRecord]) -> None:
        from dataclasses import asdict

        async with self.sessions() as session, session.begin():
            session.add_all(UsageRow(**asdict(record)) for record in records)

    async def report(
        self,
        org: str,
        team: str | None,
        since: date | None,
        until: date | None,
        group_by: Literal["team", "key", "model", "day"],
    ) -> list[dict[str, Any]]:
        from llm_gateway.tenants.models import Organization, Team

        group = {
            "team": Team.name,
            "key": UsageRow.key_id,
            "model": func.concat(UsageRow.provider, "/", UsageRow.model),
            "day": func.date(func.timezone("UTC", UsageRow.created_at)),
        }[group_by]
        columns = [
            group.label("group"),
            func.count().label("requests"),
            func.sum(UsageRow.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageRow.completion_tokens).label("completion_tokens"),
            func.sum(UsageRow.cached_tokens).label("cached_tokens"),
            func.sum(UsageRow.reasoning_tokens).label("reasoning_tokens"),
            func.sum(UsageRow.cost_usd).label("cost_usd"),
            func.count().filter(UsageRow.cost_status == "usage_missing").label("usage_missing"),
            func.count()
            .filter(UsageRow.cost_status == "stream_incomplete")
            .label("stream_incomplete"),
        ]
        query = (
            select(*columns)
            .select_from(UsageRow)
            .join(Team, Team.id == UsageRow.team_id)
            .join(Organization, Organization.id == UsageRow.organization_id)
            .where(Organization.name == org)
        )
        if team is not None:
            query = query.where(Team.name == team)
        if since is not None:
            query = query.where(UsageRow.created_at >= datetime.combine(since, time.min, UTC))
        if until is not None:
            query = query.where(
                UsageRow.created_at < datetime.combine(until + timedelta(days=1), time.min, UTC)
            )
        async with self.sessions() as session:
            rows = (await session.execute(query.group_by(group).order_by(group))).mappings().all()
        return [dict(row) for row in rows]
