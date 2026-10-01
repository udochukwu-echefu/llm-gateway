"""A secret-filled runtime must release only the public configuration allowlist."""

from dataclasses import replace

import pytest
from pydantic import SecretStr

from llm_gateway.admin.api.auth import AdminContext
from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_settings_never_disclose_secrets(admin_harness: AdminHarness) -> None:
    h = admin_harness
    ctx: AdminContext = h.app.state.admin_context
    assert ctx.settings is not None
    fake = "sk-FAKEONLY-shaped-secret-12345678901234567890"
    settings = ctx.settings.model_copy(
        update={
            "api_key_pepper": SecretStr(fake),
            "database_url": SecretStr("postgresql://fake-only:fake-only@fake.invalid/db"),
            "redis_url": SecretStr("redis://fake-only@fake.invalid"),
            "cache_encryption_key": SecretStr(fake),
        }
    )
    settings.providers.groq.api_key = SecretStr(fake)
    h.app.state.admin_context = replace(ctx, settings=settings)
    response = await h.client.get("/admin/v1/settings", headers=h.headers(h.platform_key))
    assert response.status_code == 200
    for forbidden in (
        fake,
        "pepper",
        "database_url",
        "redis_url",
        "encryption",
        "postgresql://",
        "redis://",
    ):
        assert forbidden not in response.text
    assert response.json()["providers"][0]["key_configured"] is True
    assert response.json()["limits"]["monthly_budget_usd"] == "0"
    assert (
        await h.client.get("/admin/v1/settings", headers=h.headers(h.org_key))
    ).status_code == 403


async def test_providers_label_this_replica_and_unknown_health(admin_harness: AdminHarness) -> None:
    h = admin_harness
    ctx: AdminContext = h.app.state.admin_context
    from sqlalchemy import delete

    from llm_gateway.usage.repository import UsageRow

    async with h.sessions.begin() as session:
        await session.execute(delete(UsageRow).where(UsageRow.provider == "openai"))
    h.app.state.admin_context = replace(ctx, breaker_states=lambda: {"groq": "open"})
    response = await h.client.get("/admin/v1/providers", headers=h.headers(h.platform_key))
    assert response.status_code == 200
    body = response.json()
    assert body["circuit_scope"] == "this replica"
    groq = body["data"][0]
    assert groq["circuit_breaker"] == "open"
    unused = next(row for row in body["data"] if row["provider"] == "openai")
    assert unused["15m"] == {"attempts": 0, "error_rate": None, "p95_ms": None}
