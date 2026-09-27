import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event, first_broken
from llm_gateway.audit.models import AuditEvent

pytestmark = pytest.mark.db


async def test_concurrent_appends_form_one_chain(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Hold all writers at the transaction entrance. The real lock must serialize tail reads.
    ready = 0
    gate = asyncio.Event()

    async def append(index: int) -> None:
        nonlocal ready
        async with sessions.begin() as session:
            ready += 1
            if ready == 12:
                gate.set()
            await gate.wait()
            await append_event(session, "concurrency-test", "test", "team", str(index))
            # Keep the transaction uncommitted long enough for every unlocked writer to read
            # the same previous hash. This makes removing the lock deterministically fail.
            await asyncio.sleep(0.02)

    await asyncio.gather(*(append(index) for index in range(12)))

    async with sessions() as session:
        events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
    assert first_broken(events) is None
    assert sum(event.actor == "concurrency-test" for event in events) == 12


@pytest.mark.parametrize(
    "operation", ["UPDATE audit_events SET actor = 'tampered'", "DELETE FROM audit_events"]
)
async def test_trigger_rejects_changes(
    sessions: async_sessionmaker[AsyncSession], operation: str
) -> None:
    async with sessions.begin() as session:
        event = await append_event(session, "trigger-test", "test", "team", "test")

    with pytest.raises(DBAPIError, match="append-only"):
        async with sessions.begin() as session:
            await session.execute(text(operation + " WHERE id = :id"), {"id": event.id})


async def test_verify_pinpoints_tampered_row(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        event = await append_event(session, "tamper-test", "test", "team", "test")
    async with sessions() as session:
        clean = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
    assert first_broken(clean) is None

    # Roll back the deliberate tamper so other tests share a clean chain.
    async with sessions() as session:
        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_append_only"))
        await session.execute(
            text("UPDATE audit_events SET actor = 'tampered' WHERE id = :id"), {"id": event.id}
        )
        events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
        assert first_broken(events) == event.id
        await session.rollback()
