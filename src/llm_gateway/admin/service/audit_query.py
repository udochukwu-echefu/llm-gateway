"""Shared org-scoped audit selection for pagination and exact filtered counts."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, String, or_, select

from llm_gateway.audit.models import AuditEvent
from llm_gateway.tenants.models import ApiKey, Team


def audit_query(
    role: Literal["platform", "org"],
    organization_id: uuid.UUID | None,
    since: date | None,
    until: date | None,
    action: str | None,
    actor: str | None,
    target_type: str | None,
) -> Select[AuditEvent]:
    query = select(AuditEvent)
    if role == "org":
        key_ids = select(ApiKey.key_id).join(Team).where(Team.organization_id == organization_id)
        query = query.where(
            or_(
                (AuditEvent.target_type == "organization")
                & (AuditEvent.target_id == str(organization_id)),
                (AuditEvent.target_type == "team")
                & AuditEvent.target_id.in_(
                    select(Team.id.cast(String)).where(Team.organization_id == organization_id)
                ),
                (AuditEvent.target_type == "key") & AuditEvent.target_id.in_(key_ids),
            )
        )
    if since is not None:
        query = query.where(
            AuditEvent.occurred_at >= datetime.combine(since, datetime.min.time(), UTC)
        )
    if until is not None:
        query = query.where(
            AuditEvent.occurred_at
            < datetime.combine(until + timedelta(days=1), datetime.min.time(), UTC)
        )
    if actor is not None:
        query = query.where(AuditEvent.actor == actor)
    if target_type is not None:
        query = query.where(AuditEvent.target_type == target_type)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    return query
