"""Disposable-DB boot issuance, overlap-safe expiry and wake-time append behavior."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deploy.demo.boot_keys import BOOT_KEY_PREFIX, issue_boot_keys
from llm_gateway.tenants.models import AdminKey, ApiKey
from llm_gateway.usage.repository import UsageRow
from scripts.seed_demo import seed_demo
from tests.conftest import TEST_PEPPER

pytestmark = pytest.mark.db


async def test_boot_keys_revoke_only_appliance_keys_older_than_24_hours(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    monkeypatch.setenv("GATEWAY_DEMO_SEED_SIGNIN_KEYS", "0")
    monkeypatch.setenv("GATEWAY_DEMO_KEYS_FILE", str(tmp_path / "never-written"))
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    try:
        await seed_demo(sessions, TEST_PEPPER.encode(), now)
        first = await issue_boot_keys(sessions, TEST_PEPPER.encode(), "old", now)
        overlap = await issue_boot_keys(sessions, TEST_PEPPER.encode(), "overlap", now)
        async with sessions.begin() as session:
            for model in (AdminKey, ApiKey):
                await session.execute(
                    update(model)
                    .where(model.name.startswith(BOOT_KEY_PREFIX + "old"))
                    .values(created_at=now - timedelta(hours=25))
                )
        current = await issue_boot_keys(sessions, TEST_PEPPER.encode(), "current", now)
        async with sessions() as session:
            for model in (AdminKey, ApiKey):
                rows = (await session.scalars(select(model))).all()
                assert all(
                    row.revoked_at for row in rows if row.name.startswith(BOOT_KEY_PREFIX + "old")
                )
                assert all(
                    row.revoked_at is None
                    for row in rows
                    if row.name.startswith(BOOT_KEY_PREFIX + "overlap")
                )
                assert all(
                    row.revoked_at is None or row.name.endswith("revoked")
                    for row in rows
                    if not row.name.startswith(BOOT_KEY_PREFIX)
                )
            viewers = (
                await session.scalars(
                    select(AdminKey).where(AdminKey.name.startswith(BOOT_KEY_PREFIX + "current"))
                )
            ).all()
            assert len(viewers) == 2
            assert {row.name for row in viewers} == {
                BOOT_KEY_PREFIX + "current:platform",
                BOOT_KEY_PREFIX + "current:northwind",
            }
            assert all(row.role == "viewer" for row in viewers)
            assert {row.organization_id is None for row in viewers} == {True, False}
        assert current.keys() == {"DEMO_VIEWER_KEY", "DEMO_ORG_VIEWER_KEY", "DEMO_TENANT_KEY"}
        assert not set(first.values()) & set(overlap.values())
        captured = capfd.readouterr()
        assert all(key not in captured.out + captured.err for key in current.values())
        assert not (tmp_path / "never-written").exists()
    finally:
        await engine.dispose()


async def test_wake_top_up_appends_only_missing_days_and_skips_same_day(
    migrated_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_DEMO_SEED", "1")
    monkeypatch.setenv("GATEWAY_DEMO_SEED_SIGNIN_KEYS", "0")
    monkeypatch.setenv("GATEWAY_DEMO_SEED_TOP_UP", "1")
    engine = create_async_engine(migrated_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    try:
        await seed_demo(sessions, TEST_PEPPER.encode(), now)
        async with sessions() as session:
            original = set(await session.scalars(select(UsageRow.id)))
        await seed_demo(sessions, TEST_PEPPER.encode(), now + timedelta(days=2))
        async with sessions() as session:
            rows = (await session.scalars(select(UsageRow))).all()
            count = len(rows)
            assert original <= {row.id for row in rows}
            assert {row.created_at.date() for row in rows if row.id not in original} == {
                (now + timedelta(days=1)).date(),
                (now + timedelta(days=2)).date(),
            }
        await seed_demo(sessions, TEST_PEPPER.encode(), now + timedelta(days=2, hours=1))
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UsageRow)) == count
    finally:
        await engine.dispose()
