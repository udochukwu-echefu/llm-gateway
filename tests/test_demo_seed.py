"""Local-only deterministic fixtures cover all states and rotate private demo sign-ins."""

import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.chain import first_broken
from llm_gateway.audit.models import AuditEvent
from llm_gateway.catalog import load_catalog
from llm_gateway.demo.safety import DemoSeedError, require_local_database
from llm_gateway.tenants.models import AdminKey, ApiKey, Organization, Team
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


@pytest.mark.parametrize(
    "host",
    [
        "production.fake.invalid",
        "192.0.2.10",
        "postgres.fake.invalid",
        "",
        "localhost.fake.invalid",
    ],
)
def test_demo_seed_refuses_nonlocal_database(host: str) -> None:
    with pytest.raises(DemoSeedError, match="database host must be local"):
        require_local_database(f"postgresql+asyncpg://fake:fake@{host}/fake")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "postgres"])
def test_demo_seed_accepts_only_local_database_hosts(host: str) -> None:
    require_local_database(f"postgresql+asyncpg://fake:fake@{host}/fake")


@pytest.mark.db
async def test_demo_seed_is_idempotent_covers_screens_and_rotates_keys(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    output = tmp_path / "fake-demo-keys.env"
    monkeypatch.setenv("GATEWAY_DEMO_KEYS_FILE", str(output))
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    try:
        first = await seed_demo(sessions, TEST_PEPPER.encode(), now)
        contents = output.read_text()
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        second = await seed_demo(sessions, TEST_PEPPER.encode(), now)
        assert first[0].id == second[0].id
        assert first[2] == second[2]
        assert first[2] > 3000
        assert output.read_text() != contents
        async with sessions() as session:
            orgs = (
                await session.scalars(
                    select(Organization).where(
                        Organization.name.in_(["Demo Co", "Northwind Health", "Orbit Labs"])
                    )
                )
            ).all()
            assert len(orgs) == 3
            teams = (
                await session.scalars(select(Team).where(Team.organization_id == first[0].id))
            ).all()
            assert len(teams) == 4
            keys = (
                await session.scalars(
                    select(ApiKey).where(ApiKey.team_id.in_([team.id for team in teams]))
                )
            ).all()
            assert len(keys) == 24
            assert any(key.revoked_at for key in keys)
            assert any(key.expires_at and key.expires_at < now for key in keys)
            assert any(key.expires_at and key.expires_at > now for key in keys)
            rows = (
                await session.scalars(
                    select(UsageRow).where(UsageRow.organization_id == first[0].id)
                )
            ).all()
            assert len({row.created_at.date() for row in rows}) == 90
            await session.execute(text("ANALYZE usage_records"))
            for label, sql in (
                (
                    "org timeline",
                    "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM usage_records "
                    "WHERE organization_id=:org ORDER BY created_at DESC,id DESC LIMIT 50",
                ),
                (
                    "request attempts",
                    "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM usage_records "
                    "WHERE organization_id=:org AND request_id=:request ORDER BY attempt",
                ),
            ):
                plan = list(
                    await session.scalars(
                        text(sql), {"org": first[0].id, "request": rows[0].request_id}
                    )
                )
                print(label + "\n" + "\n".join(plan))
                assert any("Index" in line for line in plan)

            assert {f"{row.provider}/{row.model}" for row in rows} == {
                f"{entry.provider}/{entry.model}" for entry in load_catalog().models
            }
            assert all(row.key_id in {key.key_id for key in keys} for row in rows)
            assert any(row.stream for row in rows)
            assert any(not row.stream for row in rows)
            assert any(row.status_code == 400 for row in rows)
            assert any(row.status_code == 502 for row in rows)
            assert any(row.cost_status == "stream_incomplete" for row in rows)
            assert any(row.cost_status == "unpriced" and row.cost_usd is None for row in rows)
            assert any(row.outcome == "cache_hit" and row.saved_usd for row in rows)
            assert any(row.redaction_count for row in rows)
            assert any(row.attempt == 3 and row.fallback_from for row in rows)
            events = (await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all()
            assert first_broken(list(events)) is None
            actions = {event.action for event in events if event.actor == "synthetic-demo-seeder"}
            assert {
                "create-org",
                "create-team",
                "create-key",
                "revoke-key",
                "create-admin-key",
                "revoke-admin-key",
                "set-limits",
                "clear-limits",
                "set-budget",
                "set-models",
                "clear-models",
                "set-guardrails",
                "clear-guardrails",
                "set-residency",
                "clear-residency",
                "cache-purge",
            } <= actions
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AdminKey)
                    .where(
                        AdminKey.name.in_(
                            ["Synthetic demo platform admin", "Synthetic Northwind org admin"]
                        ),
                        AdminKey.revoked_at.is_(None),
                    )
                )
                == 2
            )
    finally:
        await engine.dispose()


@pytest.mark.db
async def test_demo_seed_wont_populate_an_existing_non_demo_org(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    monkeypatch.setattr("scripts.seed_demo.DEMO_ORG", "Fake existing owner")
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        admin = AdminService(sessions, TEST_PEPPER.encode(), "fake-owner")
        org = await admin.create_org("Fake existing owner")
        with pytest.raises(DemoSeedError, match="not created by this seeder"):
            await seed_demo(sessions, TEST_PEPPER.encode())
        assert await admin.list_teams(org.name, None, 500) == []
    finally:
        await engine.dispose()


async def test_callable_seeder_refuses_remote_bound_engine_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    engine = create_async_engine("postgresql+asyncpg://fake:fake@remote.fake.invalid/fake")
    sessions = async_sessionmaker(engine)

    async def forbidden_io(*args: object, **kwargs: object) -> None:
        raise AssertionError("Seeder attempted I/O before refusing remote database")

    monkeypatch.setattr(AsyncSession, "execute", forbidden_io)
    try:
        with pytest.raises(DemoSeedError, match="database host must be local"):
            await seed_demo(sessions, TEST_PEPPER.encode())
    finally:
        await engine.dispose()
