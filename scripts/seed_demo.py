"""Opt-in local synthetic metadata; never calls providers or prints credentials."""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from llm_gateway.catalog import load_catalog
from llm_gateway.demo.credentials import rotate_credentials
from llm_gateway.demo.safety import DemoSeedError, require_local_database, require_local_sessions
from llm_gateway.demo.usage import usage_rows
from llm_gateway.demo.workspace import ACTOR, organization, populate
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.repository import UsageRow

DEMO_ORG = "Demo Co"
DEMO_ACTOR = ACTOR


async def seed_demo(
    sessions: async_sessionmaker[AsyncSession], pepper: bytes, now: datetime | None = None
) -> tuple[Organization, list[Team], int]:
    _opt_in()
    require_local_sessions(sessions)
    admin = AdminService(sessions, pepper, ACTOR)
    timestamp = now or datetime.now(UTC)
    async with sessions.begin() as lock:
        await lock.execute(text("SELECT pg_advisory_xact_lock(130025)"))
        first: tuple[Organization, list[Team], int] | None = None
        for name in (DEMO_ORG, "Northwind Health", "Orbit Labs"):
            org, fresh = await organization(sessions, admin, name)
            teams = await populate(admin, org, fresh, timestamp)
            key_ids = {
                team.id: [
                    key.key_id
                    for key in await admin.list_keys(org.name, team.name, None, None)
                    if key.name.endswith(("app", "batch", "expiring"))
                ]
                for team in teams
            }
            rows = usage_rows(org, teams, load_catalog(), key_ids, timestamp)
            async with sessions.begin() as session:
                for start in range(0, len(rows), 250):
                    statement = insert(UsageRow).values(
                        [asdict(row) for row in rows[start : start + 250]]
                    )
                    await session.execute(
                        statement.on_conflict_do_nothing(index_elements=[UsageRow.id])
                    )
                count = await session.scalar(
                    select(func.count())
                    .select_from(UsageRow)
                    .where(UsageRow.organization_id == org.id)
                )
            if fresh and name == DEMO_ORG:
                await _budgets(admin, org, teams, timestamp)
                await admin.purge_cache(org.name, None, cast(Redis, _EmptyCache()))
            if first is None:
                first = org, teams, int(count or 0)
        await rotate_credentials(
            admin, Path(os.environ.get("GATEWAY_DEMO_KEYS_FILE", ".demo-keys.env"))
        )
        if first is None:
            raise DemoSeedError("No synthetic workspace was created.")
        return first


async def _budgets(
    admin: AdminService, org: Organization, teams: list[Team], now: datetime
) -> None:
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with admin.sessions() as session:
        sums = dict(
            (
                await session.execute(
                    select(UsageRow.team_id, func.sum(UsageRow.cost_usd))
                    .where(UsageRow.organization_id == org.id, UsageRow.created_at >= month)
                    .group_by(UsageRow.team_id)
                )
            ).all()
        )
    for team in teams:
        if team.name not in ("Search", "Support"):
            continue
        spend = sums.get(team.id) or Decimal("0.1")
        budget = (spend / Decimal("1.1" if team.name == "Search" else "0.85")).quantize(
            Decimal("0.000000000001")
        )
        await admin.set_limits(org.name, team.name, budget=budget, alert=Decimal("0.8"))


class _EmptyCache:
    """An empty synthetic cache gives the real purge service an audited no-op."""

    async def scan_iter(self, **kwargs: object) -> AsyncIterator[bytes]:
        if False:
            yield b""

    async def unlink(self, *keys: bytes) -> int:
        return 0


def _opt_in() -> None:
    if os.environ.get("GATEWAY_DEMO_SEED") != "1":
        raise DemoSeedError("Refusing demo seed: set GATEWAY_DEMO_SEED=1 for a local database.")


async def _main() -> None:
    _opt_in()
    url = os.environ.get("GATEWAY_DATABASE_URL")
    pepper = os.environ.get("GATEWAY_API_KEY_PEPPER", "")
    if not url or len(pepper.encode()) < 32:
        raise DemoSeedError("Set the local database and a 32-byte fake demo pepper.")
    require_local_database(url)
    engine = create_async_engine(url)
    try:
        org, teams, count = await seed_demo(
            async_sessionmaker(engine, expire_on_commit=False), pepper.encode()
        )
        print(f"Synthetic workspace: {org.name}; {len(teams)} teams; {count} metadata attempts.")
        print("Demo sign-in credentials written to the ignored mode-0600 file; never printed.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except DemoSeedError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            "Demo seed failed. Check the local database and migrations; no secrets were printed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
