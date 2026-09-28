import json
import uuid
from collections.abc import AsyncIterator
from typing import cast

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from llm_gateway.admin.api.app import create_admin_app
from llm_gateway.admin.api.auth import AdminContext
from llm_gateway.audit.models import AuditEvent
from llm_gateway.config import Settings
from llm_gateway.limits.service import LimitService
from llm_gateway.main import create_app
from llm_gateway.tenants.models import Team
from tests.admin_api.conftest import AdminHarness
from tests.conftest import OfflineLimitService
from tests.tenants.support import DatabaseTestStore

pytestmark = pytest.mark.db


async def test_key_types_are_rejected_on_opposite_ports(
    admin_harness: AdminHarness, settings: Settings, migrated_database: str
) -> None:
    admin = admin_harness.client
    tenant_on_admin = await admin.get(
        "/admin/v1/orgs", headers=admin_harness.headers(admin_harness.team_key)
    )
    public_app = create_app(
        settings,
        secret_store=DatabaseTestStore(migrated_database),
        limit_service=OfflineLimitService(),
    )
    async with (
        public_app.router.lifespan_context(public_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=public_app), base_url="http://public.test"
        ) as public,
    ):
        admin_on_tenant = await public.get(
            "/v1/models", headers=admin_harness.headers(admin_harness.platform_key)
        )
        admin_path = await public.get(
            "/admin/v1/orgs", headers=admin_harness.headers(admin_harness.platform_key)
        )
        public_openapi = await public.get("/openapi.json")
    tenant_path = await admin.get(
        "/v1/models", headers=admin_harness.headers(admin_harness.platform_key)
    )
    admin_openapi = await admin.get("/openapi.json")

    assert tenant_on_admin.status_code == 401
    assert admin_on_tenant.status_code == 401
    assert admin_path.status_code == 404
    assert tenant_path.status_code == 404
    assert all(not path.startswith("/admin") for path in public_openapi.json()["paths"])
    assert all(not path.startswith("/v1") for path in admin_openapi.json()["paths"])


async def test_key_is_returned_on_creation_but_listing_has_no_secret_or_hash(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    headers = harness.headers(harness.org_key)
    created = await harness.client.post(
        f"/admin/v1/orgs/{harness.org}/teams/team/keys", json={"name": "fake-once"}, headers=headers
    )
    listed = await harness.client.get(f"/admin/v1/orgs/{harness.org}/keys", headers=headers)

    full_key = created.json()["key"]
    assert full_key.startswith("lgw_")
    assert full_key not in json.dumps(listed.json())
    assert "secret_hash" not in json.dumps(listed.json())
    assert any(row["key_id"] == created.json()["key_id"] for row in listed.json()["data"])


async def test_api_mutation_records_verified_key_actor_in_same_transaction(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    name = "audited-" + uuid.uuid4().hex
    created = await harness.client.post(
        f"/admin/v1/orgs/{harness.org}/teams",
        json={"name": name},
        headers=harness.headers(harness.org_key),
    )
    actor = "admin:" + harness.org_key.split("_")[1]
    async with harness.sessions() as session:
        team = await session.scalar(select(Team).where(Team.name == name))
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.target_id == created.json()["id"])
        )

    assert created.status_code == 200
    assert team is not None
    assert event is not None
    assert event.actor == actor
    assert event.action == "create-team"


async def test_api_mutation_rolls_back_if_audit_append_fails(
    admin_harness: AdminHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "rollback-" + uuid.uuid4().hex

    async def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("fake audit failure")

    monkeypatch.setattr("llm_gateway.tenants.repository.append_event", fail_audit)
    with pytest.raises(RuntimeError, match="fake audit failure"):
        await admin_harness.client.post(
            f"/admin/v1/orgs/{admin_harness.org}/teams",
            json={"name": name},
            headers=admin_harness.headers(admin_harness.org_key),
        )
    async with admin_harness.sessions() as session:
        team = await session.scalar(select(Team).where(Team.name == name))

    assert team is None


async def test_admin_key_revoke_takes_effect_without_tenant_key_cache(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    admin_id = harness.org_key.split("_")[1]
    revoked = await harness.client.post(
        f"/admin/v1/keys/{admin_id}/revoke", headers=harness.headers(harness.platform_key)
    )
    denied = await harness.client.get("/admin/v1/orgs", headers=harness.headers(harness.org_key))

    assert revoked.status_code == 200
    assert denied.status_code == 401


async def test_org_audit_listing_excludes_other_org_events(admin_harness: AdminHarness) -> None:
    harness = admin_harness
    own = await harness.client.post(
        f"/admin/v1/orgs/{harness.org}/teams",
        json={"name": "audit-own-" + uuid.uuid4().hex},
        headers=harness.headers(harness.platform_key),
    )
    other = await harness.client.post(
        f"/admin/v1/orgs/{harness.other}/teams",
        json={"name": "audit-other-" + uuid.uuid4().hex},
        headers=harness.headers(harness.platform_key),
    )
    listed = await harness.client.get(
        "/admin/v1/audit?page_size=500", headers=harness.headers(harness.org_key)
    )
    targets = {row["target_id"] for row in listed.json()["data"]}

    assert own.status_code == other.status_code == listed.status_code == 200
    assert own.json()["id"] in targets
    assert other.json()["id"] not in targets


async def test_duplicate_team_uses_error_envelope_without_database_details(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    response = await harness.client.post(
        f"/admin/v1/orgs/{harness.org}/teams",
        json={"name": "team"},
        headers=harness.headers(harness.org_key),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "duplicate key" not in response.text.lower()


@pytest.mark.redis
async def test_admin_auth_failures_have_separate_redis_counter(
    admin_harness: AdminHarness, test_redis: Redis, migrated_database: str
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(migrated_database)
    ip = "admin-test-" + uuid.uuid4().hex
    limits = LimitService(test_redis, ip_limit=2)
    await limits.start()
    app = create_admin_app(
        AdminContext(
            async_sessionmaker(engine), b"fake-pepper-for-tests-only-32-bytes-minimum", limits, None
        )
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(ip, 1)), base_url="http://admin.test"
        ) as client:
            first = await client.get("/admin/v1/orgs")
            second = await client.get("/admin/v1/orgs")
            third = await client.get("/admin/v1/orgs")
        admin_scan = cast(
            AsyncIterator[bytes],
            test_redis.scan_iter(match=f"lgw:admin-auth-fail:{ip}:*"),  # pyright: ignore[reportUnknownMemberType]  # redis-py types scan_iter as Unknown
        )
        tenant_scan = cast(
            AsyncIterator[bytes],
            test_redis.scan_iter(match=f"lgw:auth-fail:{ip}:*"),  # pyright: ignore[reportUnknownMemberType]  # redis-py types scan_iter as Unknown
        )
        keys = [key async for key in admin_scan]
        tenant_keys = [key async for key in tenant_scan]
    finally:
        await engine.dispose()

    assert [first.status_code, second.status_code, third.status_code] == [401, 401, 429]
    assert keys
    assert tenant_keys == []
