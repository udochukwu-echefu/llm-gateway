import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.admin import execute, parser
from llm_gateway.audit.chain import first_broken
from llm_gateway.audit.models import AuditEvent
from llm_gateway.tenants.repository import PostgresKeyRepository
from tests.conftest import TEST_PEPPER
from tests.tenants.support import run_admin

pytestmark = pytest.mark.db


async def test_every_cli_change_has_one_secret_free_event(
    sessions: async_sessionmaker[AsyncSession],
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = "operator-" + uuid.uuid4().hex
    monkeypatch.setenv("GATEWAY_ADMIN_ACTOR", actor)
    org = "audit-" + uuid.uuid4().hex
    run_admin(migrated_database, "create-org", org)
    run_admin(migrated_database, "create-team", org, "team")
    key = run_admin(migrated_database, "create-key", org, "team", "key")
    key_id = key.split("_")[1]
    run_admin(migrated_database, "revoke-key", key_id)
    run_admin(migrated_database, "set-limits", org, "team", "--rpm", "7")
    run_admin(migrated_database, "clear-limits", org, "team")
    run_admin(migrated_database, "set-budget", org, "team", "12.5")

    async with sessions() as session:
        events = list(
            (
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.actor == actor).order_by(AuditEvent.id)
                )
            ).all()
        )
    assert [e.action for e in events] == [
        "create-org",
        "create-team",
        "create-key",
        "revoke-key",
        "set-limits",
        "clear-limits",
        "set-budget",
    ]
    assert all(e.occurred_at.utcoffset() is not None for e in events)
    assert events[4].details == {"rpm": 7}
    assert events[6].details == {"monthly_budget_usd": "12.5", "alert_threshold": "0.8"}
    assert all(e.details == {} for e in events[:4])
    encoded = json.dumps([e.details for e in events])
    assert key not in encoded
    assert TEST_PEPPER not in encoded
    assert "hash" not in encoded
    assert "http" not in encoded
    listing = run_admin(
        migrated_database,
        "audit",
        "list",
        "--action",
        "set-budget",
        "--since",
        datetime.now(UTC).date().isoformat(),
    )
    assert all(json.loads(line)["action"] == "set-budget" for line in listing.splitlines())
    assert actor in listing
    assert "Audit chain verified" in run_admin(migrated_database, "audit", "verify")


async def test_failed_cli_change_writes_no_event(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    actor = str(uuid.uuid4())
    repository = PostgresKeyRepository(sessions, actor)

    with pytest.raises(ValueError, match="Team not found"):
        await execute(
            parser().parse_args(["create-key", "absent", "absent", "key"]),
            repository,
            TEST_PEPPER.encode(),
        )

    async with sessions() as session:
        assert await session.scalar(select(AuditEvent).where(AuditEvent.actor == actor)) is None
        assert (
            first_broken(
                list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
            )
            is None
        )
