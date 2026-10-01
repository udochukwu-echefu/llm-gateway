"""Postgres percentiles over recorded attempts, not gateway-overhead measurements."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.admin.request_filters import RequestFilters
from llm_gateway.admin.service.request_log import json_value
from llm_gateway.tenants.models import Team
from llm_gateway.usage.repository import UsageRow


class AnalyticsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: datetime = Field(default_factory=lambda: datetime.now(UTC) - timedelta(days=7))
    until: datetime = Field(default_factory=lambda: datetime.now(UTC))
    bucket: Literal["hour", "day"] = "day"
    group_by: Literal["provider", "model", "team"] | None = None

    _zoned = field_validator("since", "until")(RequestFilters.zoned.__func__)

    @model_validator(mode="after")
    def ordered(self) -> "AnalyticsFilters":
        if self.since > self.until or self.until - self.since > timedelta(days=366):
            raise ValueError("Analytics range must be ordered and at most 366 days")
        return self


async def analytics(
    session: AsyncSession, org_id: uuid.UUID, filters: AnalyticsFilters
) -> list[dict[str, Any]]:
    bucket = func.date_trunc(filters.bucket, func.timezone("UTC", UsageRow.created_at))
    group = {
        "provider": UsageRow.provider,
        "model": func.concat(UsageRow.provider, "/", UsageRow.model),
        "team": Team.name,
    }.get(filters.group_by or "")
    count = func.count()
    columns = [
        bucket.label("bucket"),
        count.label("requests"),
        (func.count().filter(UsageRow.status_code >= 400) * 1.0 / count).label("error_rate"),
        func.count().filter(UsageRow.fallback_from.is_not(None)).label("fallback_count"),
        func.count().filter(UsageRow.attempt > 1).label("retry_count"),
        (func.count().filter(UsageRow.outcome == "cache_hit") * 1.0 / count).label(
            "cache_hit_rate"
        ),
        func.sum(UsageRow.saved_usd).label("saved_usd"),
        func.sum(UsageRow.redaction_count).label("redaction_count"),
    ]
    for name, column in (("duration", UsageRow.duration_ms), ("ttfb", UsageRow.ttfb_ms)):
        for label, percentile in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99)):
            columns.append(
                func.percentile_cont(percentile).within_group(column).label(f"{name}_{label}")
            )
    grouping: list[ColumnElement[Any]] = [bucket]
    if group is not None:
        columns.append(group.label("group"))
        grouping.append(cast(ColumnElement[Any], group))
    query = (
        select(*columns)
        .select_from(UsageRow)
        .where(
            UsageRow.organization_id == org_id,
            UsageRow.created_at >= filters.since,
            UsageRow.created_at <= filters.until,
        )
    )
    if filters.group_by == "team":
        query = query.join(Team, Team.id == UsageRow.team_id)
    rows = (await session.execute(query.group_by(*grouping).order_by(*grouping))).mappings().all()
    return [
        {
            key: round(value, 1)
            if key.startswith(("duration_", "ttfb_")) and isinstance(value, float)
            else json_value(value)
            for key, value in row.items()
        }
        for row in rows
    ]
