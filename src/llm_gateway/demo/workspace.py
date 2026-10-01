"""Distinct demo organizations and policy stories, using the real audited service."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit.models import AuditEvent
from llm_gateway.demo.safety import DemoSeedError
from llm_gateway.tenants.models import ApiKey, Organization, Team

ACTOR = "synthetic-demo-seeder"
STORIES = {
    "Demo Co": ("Search", "Support", "Engineering", "Paused sandbox"),
    "Northwind Health": ("Clinical", "Research"),
    "Orbit Labs": ("Prototypes",),
}


async def organization(
    sessions: async_sessionmaker[AsyncSession], admin: AdminService, name: str
) -> tuple[Organization, bool]:
    async with sessions() as session:
        org = await session.scalar(select(Organization).where(Organization.name == name))
        if org is not None:
            provenance = await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.actor == ACTOR,
                    AuditEvent.action == "create-org",
                    AuditEvent.target_id == str(org.id),
                )
            )
            if provenance is None:
                raise DemoSeedError("Demo organisation exists and was not created by this seeder.")
            return org, False
    return await admin.create_org(name), True


async def populate(
    admin: AdminService, org: Organization, fresh: bool, now: datetime
) -> list[Team]:
    names = STORIES.get(org.name, STORIES["Demo Co"])
    existing = {team.name: team for team in await admin.list_teams(org.name, None, 500)}
    teams: list[Team] = []
    for name in names:
        team = existing.get(name)
        if team is None:
            team = await admin.create_team(org.name, name)
            if name == "Search":
                await admin.set_limits(org.name, name, rpm=120, tpm=60000, max_concurrency=4)
            elif name == "Engineering":
                await admin.set_limits(
                    org.name, name, rpm=0, tpm=0, max_concurrency=0, budget=Decimal(0)
                )
            if org.name != "Demo Co":
                await admin.set_limits(org.name, name, budget=Decimal("100.00"))
            await _keys(admin, org.name, name, now)
        teams.append(team)
    if fresh:
        await _policies(admin, org)
    return teams


async def _keys(admin: AdminService, org: str, team: str, now: datetime) -> None:
    for suffix in ("app", "batch", "expiring", "expired", "revoked", "never used"):
        await admin.create_key(org, team, f"Synthetic {team} {suffix}")
    keys = await admin.list_keys(org, team, None, None)
    async with admin.sessions.begin() as session:
        for key in keys:
            if key.name.endswith("expiring") or key.name.endswith("expired"):
                record = await session.get(ApiKey, key.id)
                if record is None:
                    raise DemoSeedError("Synthetic key disappeared during seeding.")
                record.expires_at = now + timedelta(days=3 if key.name.endswith("expiring") else -2)
    for key in keys:
        if key.name.endswith("revoked"):
            await admin.revoke_key(key.key_id)


async def _policies(admin: AdminService, org: Organization) -> None:
    # Exercise clear actions first; final configuration remains the documented story.
    for residency in (False, True):
        await admin.set_policy(org.name, None, residency=residency, values=None)
    await admin.set_models(org.name, None, None)
    if org.name == "Demo Co":
        await admin.set_models(
            org.name, None, ["groq/*", "deepseek/*", "gemini/*", "zai/*", "nvidia/*", "openai/*"]
        )
        await admin.set_models(org.name, "Search", ["groq/openai/gpt-oss-20b", "deepseek/*"])
        await admin.set_models(org.name, "Paused sandbox", [])
        await admin.set_policy(
            org.name,
            None,
            residency=False,
            values=["email=allow", "phone=redact", "secret_api_key=block"],
        )
        await admin.set_policy(org.name, "Engineering", residency=True, values=["sg", "global"])
        await admin.set_limits(org.name, "Support", clear=True)
    elif org.name == "Northwind Health":
        await admin.set_policy(org.name, None, residency=True, values=["eu"])
        await admin.set_policy(
            org.name,
            None,
            residency=False,
            values=[
                "email=block",
                "phone=block",
                "ip_address=block",
                "card_number=block",
                "iban=block",
            ],
        )
        await admin.set_models(org.name, None, ["gemini/*"])
