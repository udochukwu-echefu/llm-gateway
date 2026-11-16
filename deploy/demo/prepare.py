"""Dependency-aware boot stages; the supervisor itself uses only the standard library."""

import asyncio
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from deploy.demo.boot_keys import issue_boot_keys, send_boot_keys
from llm_gateway.admin.service.service import AdminService
from llm_gateway.config import Settings
from llm_gateway.usage.repository import UsageRow
from scripts.seed_demo import seed_demo

MIGRATION_LOCK = 160028
# Scale-to-zero Postgres and Redis wake on first connection and can take a while to accept
# it. Stay well inside the supervisor's 90-second bound for the whole prepare stage.
DEPENDENCY_WAIT_S = 60
MAX_RETRY_DELAY_S = 2.0
TRAFFIC_TEAM = ("Demo Co", "Support")
# The seeder leaves the traffic team at 85% of its budget: above the 80% alert, still admitted.
TRAFFIC_BUDGET_USE = Decimal("0.85")
TRAFFIC_BUDGET_REFRESH_AT = Decimal("0.9")


async def wait_dependencies() -> None:
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis-py kwargs types
        os.environ["GATEWAY_REDIS_URL"], socket_timeout=2, socket_connect_timeout=2
    )
    deadline = time.monotonic() + DEPENDENCY_WAIT_S
    delay = 0.2
    pending = "Postgres"
    try:
        while time.monotonic() < deadline:
            try:
                pending = "Postgres"
                async with asyncio.timeout(3):
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                pending = "Redis"
                async with asyncio.timeout(3):
                    await redis.ping()  # pyright: ignore[reportUnknownMemberType]  # redis-py result types
                return
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY_S)
        # Service names only: never the URL, host or driver error, which can carry credentials.
        print(f"{pending} did not accept a connection within {DEPENDENCY_WAIT_S}s.", flush=True)
        raise RuntimeError(f"Appliance dependency unavailable: {pending}.")
    finally:
        await redis.aclose()
        await engine.dispose()


async def refresh_traffic_budget(
    admin: AdminService,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> None:
    """Keep the synthetic traffic team under budget as each boot tops up the month's history.

    The seeder sets this budget once, from the spend seeded when the workspace was created.
    Daily top-ups then push later months past it and every synthetic request is refused.
    """
    org, team = TRAFFIC_TEAM
    team_id, limits = await admin.team_limits(org, team)
    budget = limits.monthly_budget_usd
    if budget is None:
        return
    timestamp = now or datetime.now(UTC)
    month = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with sessions() as session:
        spend = await session.scalar(
            select(func.sum(UsageRow.cost_usd)).where(
                UsageRow.team_id == team_id, UsageRow.created_at >= month
            )
        )
    spend = spend or Decimal(0)
    if spend < budget * TRAFFIC_BUDGET_REFRESH_AT:
        return
    target = (spend / TRAFFIC_BUDGET_USE).quantize(Decimal("0.000000000001"))
    await admin.set_limits(org, team, budget=target)


async def migrate() -> None:
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            deadline = time.monotonic() + 30
            while not await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock)"), {"lock": MIGRATION_LOCK}
            ):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Appliance migration lock unavailable.")
                await asyncio.sleep(0.2)
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    # Inherit the boot helper pipes; the parent redacts every line.
                    timeout=45,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError("Appliance migration failed.")
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock)"), {"lock": MIGRATION_LOCK}
                )
    finally:
        await engine.dispose()


async def main(stage: str) -> None:
    # Validate secrets and URLs before database I/O. Never read a mounted developer .env.
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime env supplies configuration
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pepper = os.environ["GATEWAY_API_KEY_PEPPER"].encode()
    try:
        if stage == "prepare":
            await wait_dependencies()
            await migrate()
            await seed_demo(sessions, pepper)
            admin = AdminService(sessions, pepper, "synthetic-demo-appliance")
            # Lazy seeding preserves policies; only establish the traffic policy once.
            guardrails, _ = await admin.policies("Demo Co", "Support")
            if guardrails.action("email") != "redact":
                await admin.set_policy(
                    "Demo Co", "Support", residency=False, values=["email=redact"]
                )
                await admin.set_limits("Demo Co", "Support", rpm=5, tpm=10000, max_concurrency=1)
            await refresh_traffic_budget(admin, sessions)
        elif stage == "keys":
            keys = await issue_boot_keys(sessions, pepper, os.environ["DEMO_BOOT_ID"])
            send_boot_keys(keys, int(os.environ["DEMO_BOOT_KEY_FD"]))
        else:
            raise ValueError("Unknown appliance boot stage.")
        settings.validate_demo_providers()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1]))
    except Exception:
        raise SystemExit("Appliance boot stage failed; no credentials were printed.") from None
