"""Synthetic metadata for realistic screenshots, with runtime-only admin keys."""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.chain import append_event
from llm_gateway.usage.record import UsageRecord
from llm_gateway.usage.repository import PostgresUsageRepository


async def main() -> None:
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    admin = AdminService(
        sessions, os.environ["GATEWAY_API_KEY_PEPPER"].encode(), "synthetic-console-fixture"
    )
    org = await admin.create_org("Demo workspace")
    team = await admin.create_team(org.name, "Search")
    await admin.create_org("Other workspace")
    await admin.create_team("Other workspace", "Private team")
    await admin.set_limits(org.name, team.name, budget=Decimal("100"), alert=Decimal("0.8"))
    platform = await admin.create_admin_key("Fake platform operator", "platform", None)
    org_key = await admin.create_admin_key("Fake org operator", "org", org.name)
    revocable = await admin.create_admin_key("Fake revocable operator", "org", org.name)
    async with sessions.begin() as session:
        for _ in range(26):
            await append_event(
                session, "synthetic-console-fixture", "fixture-health", "organization", str(org.id)
            )
    now = datetime.now(UTC)
    rows = [
        UsageRecord(
            uuid.uuid4(),
            f"synthetic-request-{index}",
            now.replace(day=max(1, now.day - index)),
            org.id,
            team.id,
            "fakepublicid",
            "groq",
            "openai/gpt-oss-20b",
            "chat",
            False,
            200,
            "cache_hit" if index == 1 else "success",
            "usage_missing" if index == 0 else "priced",
            None if index == 0 else 1200,
            None if index == 0 else 300,
            0,
            0,
            None if index == 0 else Decimal("2.35"),
            "synthetic",
            20.0,
            None,
            saved_usd=Decimal("1.25") if index == 1 else None,
        )
        for index in range(5)
    ]
    await PostgresUsageRepository(sessions).insert(rows)
    await asyncio.to_thread(
        write_state,
        {
            "platform": platform,
            "orgKey": org_key,
            "revocable": revocable,
            "org": org.name,
            "other": "Other workspace",
        },
    )
    await engine.dispose()


def write_state(data: dict[str, str]) -> None:
    state = Path(os.environ["CONSOLE_STATE_FILE"])
    state.touch(mode=0o600)
    state.chmod(0o600)
    state.write_text(json.dumps(data))


if __name__ == "__main__":
    asyncio.run(main())
