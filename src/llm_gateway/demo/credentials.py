"""Rotate only seeder-owned admin keys; never print credentials."""

import os
from pathlib import Path

from sqlalchemy import select

from llm_gateway.admin.service.service import AdminService
from llm_gateway.tenants.models import AdminKey

NAMES = ("Synthetic demo platform admin", "Synthetic Northwind org admin")


async def rotate_credentials(admin: AdminService, output: Path) -> None:
    async with admin.sessions() as session:
        old = (
            await session.scalars(
                select(AdminKey).where(AdminKey.name.in_(NAMES), AdminKey.revoked_at.is_(None))
            )
        ).all()
    if not old:
        retired = await admin.create_admin_key("Synthetic retired bootstrap", "platform", None)
        await admin.revoke_key(retired.split("_")[1])
    for key in old:
        await admin.revoke_key(key.key_id)
    platform = await admin.create_admin_key(NAMES[0], "platform", None)
    org = await admin.create_admin_key(NAMES[1], "org", "Northwind Health")
    # O_NOFOLLOW rejects symlinks; truncate only after restrictive permissions are applied.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.ftruncate(fd, 0)
        with os.fdopen(fd, "w", closefd=False) as file:
            file.write(f"DEMO_PLATFORM_ADMIN_KEY={platform}\nDEMO_ORG_ADMIN_KEY={org}\n")
    finally:
        os.close(fd)
