"""Dependency-aware boot stages; the supervisor itself uses only the standard library."""

import asyncio
import os
import subprocess
import sys
import time

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deploy.demo.boot_keys import issue_boot_keys, send_boot_keys
from llm_gateway.admin.service.service import AdminService
from llm_gateway.config import Settings
from scripts.seed_demo import seed_demo

MIGRATION_LOCK = 160028


async def wait_dependencies() -> None:
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis-py kwargs types
        os.environ["GATEWAY_REDIS_URL"], socket_timeout=2, socket_connect_timeout=2
    )
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            try:
                async with asyncio.timeout(3):
                    async with engine.connect() as connection:
                        await connection.execute(text("SELECT 1"))
                    await redis.ping()  # pyright: ignore[reportUnknownMemberType]  # redis-py result types
                return
            except Exception:
                await asyncio.sleep(0.2)
        raise RuntimeError("Appliance dependencies unavailable.")
    finally:
        await redis.aclose()
        await engine.dispose()


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
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
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
