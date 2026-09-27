import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import append_event
from llm_gateway.audit.models import AuditEvent
from llm_gateway.tenants.models import Organization
from llm_gateway.tenants.repository import PostgresKeyRepository

pytestmark = pytest.mark.db


async def test_audit_failure_rolls_back_change(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, name = str(uuid.uuid4()), str(uuid.uuid4())

    async def failed_audit(
        session: AsyncSession, actor: str, action: str, target_type: str, target_id: str
    ) -> None:
        await append_event(session, actor, action, target_type, target_id)
        raise ValueError("audit write failed after insert")

    monkeypatch.setattr("llm_gateway.tenants.repository.append_event", failed_audit)

    with pytest.raises(ValueError, match="audit write failed"):
        await PostgresKeyRepository(sessions, actor).create_org(name)

    async with sessions() as session:
        assert await session.scalar(select(Organization).where(Organization.name == name)) is None
        assert await session.scalar(select(AuditEvent).where(AuditEvent.actor == actor)) is None


async def test_change_failure_rolls_back_audit(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, name = str(uuid.uuid4()), str(uuid.uuid4())

    async def fail_after_audit(
        session: AsyncSession, actor: str, action: str, target_type: str, target_id: str
    ) -> None:
        await append_event(session, actor, action, target_type, target_id)
        session.add(Organization(name=name))  # duplicate fails when the change commits

    monkeypatch.setattr("llm_gateway.tenants.repository.append_event", fail_after_audit)

    with pytest.raises(IntegrityError):
        await PostgresKeyRepository(sessions, actor).create_org(name)

    async with sessions() as session:
        assert await session.scalar(select(Organization).where(Organization.name == name)) is None
        assert await session.scalar(select(AuditEvent).where(AuditEvent.actor == actor)) is None
