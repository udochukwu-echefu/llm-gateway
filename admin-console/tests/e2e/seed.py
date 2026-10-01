"""Synthetic metadata for realistic screenshots, with runtime-only admin keys."""

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.chain import append_event


async def main() -> None:
    engine = create_async_engine(os.environ["GATEWAY_DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    admin = AdminService(
        sessions, os.environ["GATEWAY_API_KEY_PEPPER"].encode(), "synthetic-console-fixture"
    )
    org = await admin.authorize_org("Demo Co")
    await admin.create_org("Other workspace")
    await admin.create_team("Other workspace", "Private team")
    platform = await admin.create_admin_key("Fake platform operator", "platform", None)
    org_key = await admin.create_admin_key("Fake org operator", "org", org.name)
    demo_values = dict(
        line.split("=", 1)
        for line in (
            await asyncio.to_thread(Path(os.environ["GATEWAY_DEMO_KEYS_FILE"]).read_text)
        ).splitlines()
    )
    revocable = await admin.create_admin_key("Fake revocable operator", "org", org.name)
    async with sessions.begin() as session:
        for _ in range(26):
            await append_event(
                session, "synthetic-console-fixture", "fixture-health", "organization", str(org.id)
            )
    await asyncio.to_thread(
        write_state,
        {
            "platform": platform,
            "demoPlatform": demo_values["DEMO_PLATFORM_ADMIN_KEY"],
            "demoOrg": demo_values["DEMO_ORG_ADMIN_KEY"],
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
