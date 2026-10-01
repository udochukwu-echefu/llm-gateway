"""Per-boot hashed credentials; plaintext exists only in memory and an anonymous pipe."""

import json
import os
import stat
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.admin.service.service import AdminService
from llm_gateway.tenants.models import AdminKey, ApiKey

BOOT_KEY_PREFIX = "Appliance demo boot "


async def issue_boot_keys(
    sessions: async_sessionmaker[AsyncSession],
    pepper: bytes,
    boot_id: str,
    now: datetime | None = None,
) -> dict[str, str]:
    admin = AdminService(sessions, pepper, "synthetic-demo-appliance")
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=24)
    async with sessions() as session:
        old_viewers = await session.scalars(
            select(AdminKey.key_id).where(
                AdminKey.name.startswith(BOOT_KEY_PREFIX),
                AdminKey.role == "viewer",
                AdminKey.created_at < cutoff,
                AdminKey.revoked_at.is_(None),
            )
        )
        old_tenants = await session.scalars(
            select(ApiKey.key_id).where(
                ApiKey.name.startswith(BOOT_KEY_PREFIX),
                ApiKey.created_at < cutoff,
                ApiKey.revoked_at.is_(None),
            )
        )
        old = list(old_viewers) + list(old_tenants)
    for key_id in old:
        await admin.revoke_key(key_id)
    name = BOOT_KEY_PREFIX + boot_id
    return {
        "DEMO_VIEWER_KEY": await admin.create_admin_key(name + ":platform", "viewer", None),
        "DEMO_ORG_VIEWER_KEY": await admin.create_admin_key(
            name + ":northwind", "viewer", "Northwind Health"
        ),
        "DEMO_TENANT_KEY": await admin.create_key("Demo Co", "Support", name + ":traffic"),
    }


def send_boot_keys(keys: dict[str, str], descriptor: int) -> None:
    # This descriptor is an anonymous parent-child pipe, never stdout or a filesystem path.
    if descriptor in {0, 1, 2} or not stat.S_ISFIFO(os.fstat(descriptor).st_mode):
        raise ValueError("Boot credentials require a private pipe.")
    os.write(descriptor, json.dumps(keys).encode())
