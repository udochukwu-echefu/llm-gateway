"""Indexed, org-scoped metadata queries, with stable timestamp/ID cursors."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.admin.request_filters import RequestFilters, decode_cursor, encode_cursor
from llm_gateway.tenants.models import Team
from llm_gateway.usage.repository import UsageRow


def filtered(org_id: uuid.UUID, filters: RequestFilters) -> Select[UsageRow]:
    query = select(UsageRow).where(UsageRow.organization_id == org_id)
    for name in (
        "provider",
        "model",
        "key_id",
        "alias",
        "endpoint",
        "outcome",
        "cost_status",
        "stream",
    ):
        value = getattr(filters, name)
        if value is not None:
            query = query.where(getattr(UsageRow, name) == value)
    if filters.team is not None:
        query = query.join(Team, Team.id == UsageRow.team_id).where(Team.name == filters.team)
    if filters.since is not None:
        query = query.where(UsageRow.created_at >= filters.since)
    if filters.until is not None:
        query = query.where(UsageRow.created_at <= filters.until)
    if filters.status:
        if filters.status.endswith("xx"):
            low = int(filters.status[0]) * 100
            query = query.where(UsageRow.status_code.between(low, low + 99))
        else:
            query = query.where(UsageRow.status_code == int(filters.status))
    for value, condition in (
        (filters.cache_hit, UsageRow.outcome == "cache_hit"),
        (filters.redacted, func.coalesce(UsageRow.redaction_count, 0) > 0),
        (filters.fallback, UsageRow.fallback_from.is_not(None)),
        (filters.retried, UsageRow.attempt > 1),
    ):
        if value is not None:
            query = query.where(condition if value else ~condition)
    if filters.min_latency is not None:
        query = query.where(UsageRow.duration_ms >= filters.min_latency)
    return query


async def request_page(
    session: AsyncSession, org_id: uuid.UUID, filters: RequestFilters
) -> dict[str, object]:
    query = filtered(org_id, filters)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    if filters.cursor:
        created, row_id = decode_cursor(filters.cursor)
        query = query.where(tuple_(UsageRow.created_at, UsageRow.id) < tuple_(created, row_id))
    rows = list(
        (
            await session.scalars(
                query.order_by(UsageRow.created_at.desc(), UsageRow.id.desc()).limit(
                    filters.page_size + 1
                )
            )
        ).all()
    )
    visible = rows[: filters.page_size]
    return {
        "data": [metadata(row) for row in visible],
        "total": total,
        "next_cursor": encode_cursor(visible[-1].created_at, visible[-1].id)
        if len(rows) > filters.page_size
        else None,
    }


def metadata(row: UsageRow) -> dict[str, Any]:
    # Enumerate receipt columns, never a request/response body or a key-table join.
    return {
        column.name: (
            round(value, 1)
            if column.name in {"duration_ms", "ttfb_ms"} and isinstance(value, float)
            else json_value(value)
        )
        for column in UsageRow.__table__.columns
        for value in (getattr(row, column.name),)
    }


def json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value
