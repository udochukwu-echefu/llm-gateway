"""Org key inventory filters use last-use timestamps from metadata receipts."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.tenants.models import ApiKey, Team
from llm_gateway.usage.repository import UsageRow


class KeyFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str | None = Field(default=None, max_length=128)
    team: str | None = Field(default=None, max_length=256)
    status: Literal["active", "expiring", "expired", "revoked", "never-used"] | None = None
    cursor: uuid.UUID | None = None
    page_size: int = Field(default=50, ge=1, le=500)


async def key_page(
    session: AsyncSession, org_id: uuid.UUID, filters: KeyFilters
) -> dict[str, object]:
    used = (
        select(func.max(UsageRow.created_at))
        .where(UsageRow.organization_id == org_id, UsageRow.key_id == ApiKey.key_id)
        .correlate(ApiKey)
        .scalar_subquery()
    )
    query = (
        select(ApiKey, used.label("last_used_at")).join(Team).where(Team.organization_id == org_id)
    )
    now = datetime.now(UTC)
    active = (ApiKey.revoked_at.is_(None)) & (
        (ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > now)
    )
    conditions = {
        "active": active,
        "expiring": active & (ApiKey.expires_at <= now + timedelta(days=7)),
        "expired": ApiKey.revoked_at.is_(None) & (ApiKey.expires_at <= now),
        "revoked": ApiKey.revoked_at.is_not(None),
        "never-used": used.is_(None),
    }
    if filters.status:
        query = query.where(conditions[filters.status])
    if filters.team:
        query = query.where(Team.name == filters.team)
    if filters.q:
        pattern = (
            "%" + filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
        query = query.where(
            or_(ApiKey.name.ilike(pattern, escape="\\"), ApiKey.key_id.ilike(pattern, escape="\\"))
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    if filters.cursor:
        query = query.where(ApiKey.id > filters.cursor)
    rows = (await session.execute(query.order_by(ApiKey.id).limit(filters.page_size + 1))).all()
    visible = rows[: filters.page_size]
    return {
        "data": [
            {
                "id": str(key.id),
                "key_id": key.key_id,
                "name": key.name,
                "team_id": str(key.team_id),
                "created_at": key.created_at.isoformat(),
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
                "last_used_at": last_used.isoformat() if last_used else None,
            }
            for key, last_used in visible
        ],
        "total": total,
        "next_cursor": str(visible[-1][0].id) if len(rows) > filters.page_size else None,
    }
