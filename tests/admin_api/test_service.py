"""Direct service checks keep both front ends on one audited operation path."""

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from llm_gateway.admin_service.service import AdminService
from llm_gateway.tenants.models import Organization
from tests.admin_api.conftest import AdminHarness, EmptyCache
from tests.conftest import TEST_PEPPER

pytestmark = pytest.mark.db


async def test_shared_service_operations_and_audit_chain(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    admin = AdminService(harness.sessions, TEST_PEPPER.encode(), "service-test")
    new_org = "service-" + uuid.uuid4().hex
    created_org = await admin.create_org(new_org)
    created_team = await admin.create_team(new_org, "team")
    full_key = await admin.create_key(new_org, "team", "fake-service-key")
    key_id = full_key.split("_")[1]
    await admin.set_limits(new_org, "team", rpm=11)
    await admin.set_models(new_org, None, [])
    await admin.set_policy(new_org, None, residency=False, values=[])
    await admin.set_policy(new_org, None, residency=True, values=[])
    purged = await admin.purge_cache(new_org, "team", cast(Redis, EmptyCache()))
    revoked = await admin.revoke_key(key_id)
    issued_admin = await admin.create_admin_key("fake-service-admin", "org", new_org)
    orgs = await admin.list_orgs(None, 500)
    teams = await admin.list_teams(new_org, None, 500)
    keys = await admin.list_keys(new_org, None, None, 500)
    team_id, limits = await admin.team_limits(new_org, "team")
    usage = await admin.usage(new_org, None, None, None, "team")
    audit = await admin.list_audit(None, None, None, 500)
    count, broken = await admin.verify_audit()

    assert created_org.id in {row.id for row in orgs}
    assert created_team.id in {row.id for row in teams}
    assert key_id in {row.key_id for row in keys}
    assert team_id == created_team.id
    assert limits.rpm == 11
    assert purged == 0
    assert revoked
    assert issued_admin.startswith("lgwa_")
    assert usage == []
    assert count >= len(audit)
    assert broken is None
    actions = {event.action for event in audit if event.actor == "service-test"}
    assert actions == {
        "create-org",
        "create-team",
        "create-key",
        "set-limits",
        "set-models",
        "set-guardrails",
        "set-residency",
        "cache-purge",
        "revoke-key",
        "create-admin-key",
    }


async def test_service_org_scope_rejects_other_org_reads_and_writes(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    async with harness.sessions() as session:
        owner = await session.scalar(select(Organization).where(Organization.name == harness.org))
    assert owner is not None
    admin = AdminService(harness.sessions, TEST_PEPPER.encode(), "service-org", "org", owner.id)

    with pytest.raises(ValueError, match="Organization not found"):
        await admin.list_teams(harness.other, None, 50)
    with pytest.raises(ValueError, match="Organization not found"):
        await admin.create_team(harness.other, "forbidden")
