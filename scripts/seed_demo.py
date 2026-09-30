"""Opt-in synthetic local workspace. No provider calls or recoverable key output."""

import asyncio
import os
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.models import AuditEvent
from llm_gateway.catalog import Catalog, load_catalog
from llm_gateway.cost import compute_cost
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.record import UsageRecord
from llm_gateway.usage.repository import UsageRow

DEMO_ORG = "Demo Co"
DEMO_ACTOR = "synthetic-demo-seeder"
TEAM_NAMES = ("Search", "Support", "Engineering")


class DemoSeedError(ValueError):
    """Only these intentionally safe messages may be printed by the CLI."""


async def seed_demo(
    sessions: async_sessionmaker[AsyncSession], pepper: bytes, now: datetime | None = None
) -> tuple[Organization, list[Team], int]:
    if os.environ.get("GATEWAY_DEMO_SEED") != "1":
        raise DemoSeedError("Refusing demo seed: set GATEWAY_DEMO_SEED=1 for a local database.")
    admin = AdminService(sessions, pepper, DEMO_ACTOR)
    # One transaction-scoped pen serializes concurrent seed runs; service mutations
    # use their own transactions while this connection owns the seeder's lock.
    async with sessions.begin() as lock:
        await lock.execute(text("SELECT pg_advisory_xact_lock(130025)"))
        org = await _organization(sessions, admin)
        teams = await _teams(admin)
        catalog = load_catalog()
        rows = _usage(org, teams, catalog, now or datetime.now(UTC))
        async with sessions.begin() as session:
            statement = insert(UsageRow).values([asdict(row) for row in rows])
            await session.execute(statement.on_conflict_do_nothing(index_elements=[UsageRow.id]))
            count = await session.scalar(
                select(func.count()).select_from(UsageRow).where(UsageRow.organization_id == org.id)
            )
        return org, teams, int(count or 0)


async def _organization(
    sessions: async_sessionmaker[AsyncSession], admin: AdminService
) -> Organization:
    async with sessions() as session:
        org = await session.scalar(select(Organization).where(Organization.name == DEMO_ORG))
        if org is not None:
            created_by_demo = await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.actor == DEMO_ACTOR,
                    AuditEvent.action == "create-org",
                    AuditEvent.target_id == str(org.id),
                )
            )
            if created_by_demo is None:
                raise DemoSeedError("Demo Co already exists and was not created by this seeder.")
            return org
    return await admin.create_org(DEMO_ORG)


async def _teams(admin: AdminService) -> list[Team]:
    existing = {team.name: team for team in await admin.list_teams(DEMO_ORG, None, 500)}
    teams: list[Team] = []
    for index, name in enumerate(TEAM_NAMES):
        team = existing.get(name)
        if team is None:
            team = await admin.create_team(DEMO_ORG, name)
            await admin.set_limits(
                DEMO_ORG,
                name,
                rpm=120 + index * 60,
                tpm=60000 + index * 30000,
                max_concurrency=4 + index,
                budget=Decimal(("0.25", "5.00", "10.00")[index]),
                alert=Decimal("0.8"),
            )
        keys = await admin.list_keys(DEMO_ORG, name, None, None)
        names = {key.name for key in keys}
        for key_name in (f"Synthetic {name} app", f"Synthetic {name} batch"):
            if key_name not in names:
                # The secret is deliberately discarded: no usable demo key is printed/stored.
                await admin.create_key(DEMO_ORG, name, key_name)
        teams.append(team)
    return teams


def _usage(
    org: Organization, teams: list[Team], catalog: Catalog, now: datetime
) -> list[UsageRecord]:
    rows: list[UsageRecord] = []
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for day in range(30):
        for team_index, team in enumerate(teams):
            for sample in range(4 + (29 - day) // 3 + team_index):
                rows.append(_sample(org, team, catalog, start, now, day, team_index, sample))
    return rows


def _sample(
    org: Organization,
    team: Team,
    catalog: Catalog,
    start: datetime,
    now: datetime,
    day: int,
    team_index: int,
    sample: int,
) -> UsageRecord:
    entry = catalog.models[(day + team_index + sample) % len(catalog.models)]
    created = start - timedelta(days=day) + timedelta(hours=min(now.hour, sample))
    label = f"demo-v1:{team.name}:{created.date()}:{sample}"
    usage_missing = (day + sample + team_index) % 19 == 0
    cached = not usage_missing and (day + sample) % 5 == 0
    prompt = 1800 + (29 - day) * 100 + sample * 90
    completion = 450 + sample * 40 if entry.kind == "chat" else 0
    # This is illustrative synthetic history priced at today's reviewed rates.
    price = entry.at(now)
    cost = compute_cost(price, prompt, completion, 0) if price and not price.unpriced else None
    unknown = usage_missing or price is None
    return UsageRecord(
        id=uuid.uuid5(org.id, label),
        request_id=label,
        created_at=created,
        organization_id=org.id,
        team_id=team.id,
        key_id="demopublicid",
        provider=entry.provider,
        model=entry.model,
        endpoint="chat" if entry.kind == "chat" else "embeddings",
        stream=False,
        status_code=200,
        outcome="cache_hit" if cached else "success",
        cost_status=(
            "usage_missing"
            if unknown
            else "cached"
            if cached
            else "unpriced"
            if cost is None
            else "priced"
        ),
        prompt_tokens=None if unknown else prompt,
        completion_tokens=None if unknown else completion,
        cached_tokens=None if unknown else 0,
        reasoning_tokens=None if unknown else 0,
        cost_usd=None if unknown else Decimal(0) if cached else cost,
        catalog_version=catalog.version,
        duration_ms=18.0 if cached else 240.0,
        ttfb_ms=None,
        saved_usd=cost if cached else None,
    )


async def _main() -> None:
    if os.environ.get("GATEWAY_DEMO_SEED") != "1":
        raise DemoSeedError("Refusing demo seed: set GATEWAY_DEMO_SEED=1 for a local database.")
    url = os.environ.get("GATEWAY_DATABASE_URL")
    pepper = os.environ.get("GATEWAY_API_KEY_PEPPER", "")
    if not url or len(pepper.encode()) < 32:
        raise DemoSeedError(
            "Set the local GATEWAY_DATABASE_URL and a 32-byte GATEWAY_API_KEY_PEPPER."
        )
    engine = create_async_engine(url)
    try:
        org, teams, _ = await seed_demo(
            async_sessionmaker(engine, expire_on_commit=False), pepper.encode()
        )
        print(f"Organisation: {org.id} {org.name}")
        for team in teams:
            print(f"Team: {team.id} {team.name}")
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
