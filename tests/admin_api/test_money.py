"""Administrative money stays exact and human-readable, including PostgreSQL zero sums."""

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import select

from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.repository import PostgresUsageRepository
from tests.admin_api.conftest import AdminHarness
from tests.usage.test_writer import sample_record

pytestmark = pytest.mark.db


async def test_zero_embeddings_cost_uses_fixed_point_not_exponent(
    admin_harness: AdminHarness,
) -> None:
    h = admin_harness
    async with h.sessions() as session:
        team = await session.scalar(
            select(Team).join(Organization).where(Organization.name == h.org)
        )
    assert team is not None
    await PostgresUsageRepository(h.sessions).insert(
        [
            replace(
                sample_record(),
                organization_id=team.organization_id,
                team_id=team.id,
                endpoint="embeddings",
                provider="openai",
                model="text-embedding-3-small",
                completion_tokens=0,
                cost_usd=Decimal("0E-12"),
                saved_usd=Decimal("0E-12"),
            )
        ]
    )

    response = await h.client.get(
        f"/admin/v1/orgs/{h.org}/usage?group_by=model", headers=h.headers(h.org_key)
    )

    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["group"] == "openai/text-embedding-3-small"
    assert row["cost_usd"] == "0.000000000000"
    assert row["saved_usd"] == "0.000000000000"
    assert "0E-12" not in response.text


@pytest.mark.parametrize("usd", ["0E-12", "1E-12", "1E+2"])
async def test_budget_and_new_audit_money_use_fixed_point(
    admin_harness: AdminHarness, usd: str
) -> None:
    h = admin_harness
    path = f"/admin/v1/orgs/{h.org}/teams/team/budget"
    updated = await h.client.put(
        path, headers=h.headers(h.org_key), json={"usd": usd, "alert_at": "8E-1"}
    )
    loaded = await h.client.get(path, headers=h.headers(h.org_key))
    audit = await h.client.get("/admin/v1/audit?action=set-budget", headers=h.headers(h.org_key))

    assert updated.status_code == loaded.status_code == audit.status_code == 200
    assert updated.json()["usd"] == format(Decimal(usd), "f")
    assert updated.json()["alert_at"] == "0.8"
    for source in ("overrides", "effective"):
        assert loaded.json()[source]["usd"] == format(Decimal(usd).quantize(Decimal("1E-12")), "f")
        assert "E" not in loaded.json()[source]["alert_at"]
    assert len(audit.json()["data"]) == 1
    assert audit.json()["data"][0]["details"] == {
        "monthly_budget_usd": format(Decimal(usd), "f"),
        "alert_threshold": "0.8",
    }
