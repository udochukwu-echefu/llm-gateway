"""Serialize appends in the caller's transaction so concurrent writers cannot fork."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llm_gateway.audit.models import AuditEvent

GENESIS = "0" * 64
LOCK_ID = 0x4C47574155444954


async def append_event(
    session: AsyncSession,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    details: dict[str, str | int | None] | None = None,
) -> AuditEvent:
    # Acquire before reading the tail; release only with the caller's commit/rollback.
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": LOCK_ID})
    previous = await session.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))
    event_id = await session.scalar(
        text("SELECT nextval(pg_get_serial_sequence('audit_events', 'id'))")
    )
    event = AuditEvent(
        id=event_id,
        occurred_at=datetime.now(UTC),
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        prev_hash=previous or GENESIS,
    )
    event.hash = event_hash(event)
    session.add(event)
    await session.flush()
    return event


def event_hash(event: AuditEvent) -> str:
    encoded = json.dumps(
        {
            "id": event.id,
            "occurred_at": event.occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
            "actor": event.actor,
            "action": event.action,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "details": event.details,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256((event.prev_hash + encoded).encode("utf-8")).hexdigest()


def first_broken(events: list[AuditEvent]) -> int | None:
    previous = GENESIS
    for event in events:
        if event.prev_hash != previous or event.hash != event_hash(event):
            return event.id
        previous = event.hash
    return None
