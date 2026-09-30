"""Development fixtures are opt-in, repeatable and contain only synthetic metadata."""

import os
import subprocess
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.audit.models import AuditEvent
from llm_gateway.tenants.models import ApiKey, Organization, Team
from llm_gateway.usage.repository import UsageRow
from scripts.seed_demo import seed_demo
from tests.conftest import TEST_PEPPER


def test_demo_seed_refuses_without_explicit_opt_in() -> None:
    env = {name: value for name, value in os.environ.items() if name != "GATEWAY_DEMO_SEED"}
    result = subprocess.run(
        [".venv/bin/python", "scripts/seed_demo.py"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Refusing demo seed" in result.stderr
    assert result.stdout == ""


@pytest.mark.db
async def test_demo_seed_is_idempotent_and_has_priced_unpriced_and_cache_rows(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 9, 30, 12, tzinfo=UTC)
    try:
        first = await seed_demo(sessions, TEST_PEPPER.encode(), now)
        async with sessions() as session:
            before = await session.scalar(select(func.count()).select_from(AuditEvent))
        second = await seed_demo(sessions, TEST_PEPPER.encode(), now)

        assert first[0].id == second[0].id
        assert first[2] == second[2] == 855
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Organization)
                    .where(Organization.name == "Demo Co")
                )
                == 1
            )
            team_ids = select(Team.id).where(Team.organization_id == first[0].id)
            assert (
                await session.scalar(
                    select(func.count()).select_from(ApiKey).where(ApiKey.team_id.in_(team_ids))
                )
                == 6
            )
            rows = list(
                (
                    await session.scalars(
                        select(UsageRow).where(UsageRow.organization_id == first[0].id)
                    )
                ).all()
            )
            assert any(row.cost_usd is None for row in rows)
            unpriced = [row for row in rows if row.cost_status == "unpriced"]
            assert {row.model for row in unpriced} == {
                "moonshotai/kimi-k3",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
            }
            assert all(row.cost_usd is None and row.prompt_tokens is not None for row in unpriced)
            assert any(
                row.cost_status == "usage_missing" and row.prompt_tokens is None for row in rows
            )
            assert any(row.cost_usd is not None and row.cost_usd > 0 for row in rows)
            assert any(row.outcome == "cache_hit" for row in rows)
            assert len({row.created_at.date() for row in rows}) == 30
            assert len({row.model for row in rows}) > 2
            assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before
    finally:
        await engine.dispose()


@pytest.mark.db
async def test_demo_seed_wont_populate_an_existing_non_demo_org(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from llm_gateway.admin.service.service import AdminService
    from scripts.seed_demo import DEMO_ORG, DemoSeedError

    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    monkeypatch.setattr("scripts.seed_demo.DEMO_ORG", DEMO_ORG + " existing owner")
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        admin = AdminService(sessions, TEST_PEPPER.encode(), "fake-owner")
        org = await admin.create_org(DEMO_ORG + " existing owner")
        with pytest.raises(DemoSeedError, match="not created by this seeder"):
            await seed_demo(sessions, TEST_PEPPER.encode())
        assert await admin.list_teams(org.name, None, 500) == []
    finally:
        await engine.dispose()
