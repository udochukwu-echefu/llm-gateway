"""Org-scoped team summaries avoid multiplying usage by key-table joins."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.admin.service.limits import admin_defaults
from llm_gateway.tenants.models import ApiKey, Team, TeamLimits
from llm_gateway.usage.repository import UsageRow


async def team_page(
    sessions: async_sessionmaker[AsyncSession],
    organization_id: uuid.UUID,
    rows: list[Team],
    page_size: int,
) -> dict[str, object]:
    month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with sessions() as session:
        total = await session.scalar(
            select(func.count()).select_from(Team).where(Team.organization_id == organization_id)
        )
        spend = dict(
            (
                await session.execute(
                    select(UsageRow.team_id, func.sum(UsageRow.cost_usd))
                    .where(
                        UsageRow.team_id.in_([row.id for row in rows]), UsageRow.created_at >= month
                    )
                    .group_by(UsageRow.team_id)
                )
            ).all()
        )
        activity = dict(
            (
                await session.execute(
                    select(UsageRow.team_id, func.max(UsageRow.created_at))
                    .where(UsageRow.team_id.in_([row.id for row in rows]))
                    .group_by(UsageRow.team_id)
                )
            ).all()
        )
        keys = dict(
            (
                await session.execute(
                    select(ApiKey.team_id, func.count())
                    .where(ApiKey.team_id.in_([row.id for row in rows]))
                    .group_by(ApiKey.team_id)
                )
            ).all()
        )
        limits = {
            row.team_id: row
            for row in (
                await session.scalars(
                    select(TeamLimits).where(TeamLimits.team_id.in_([row.id for row in rows]))
                )
            ).all()
        }
    defaults = admin_defaults()
    result = _page(
        [
            {
                "id": str(row.id),
                "organization_id": str(row.organization_id),
                "spend_usd": format(spend[row.id], "f")
                if spend.get(row.id) is not None
                else None
                if row.id in spend
                else "0",
                "budget_usd": format(
                    limits[row.id].monthly_budget_usd
                    if row.id in limits and limits[row.id].monthly_budget_usd is not None
                    else defaults.default_monthly_budget_usd,
                    "f",
                ),
                "key_count": keys.get(row.id, 0),
                "last_activity": activity[row.id].isoformat() if activity.get(row.id) else None,
                "name": row.name,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        page_size,
    )

    result["total"] = total
    return result


def _page(items: list[dict[str, object]], size: int) -> dict[str, object]:
    visible = items[:size]
    return {"data": visible, "next_cursor": str(visible[-1]["id"]) if len(items) > size else None}
