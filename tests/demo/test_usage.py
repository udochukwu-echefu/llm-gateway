"""Recovery demo receipts must describe a coherent, non-cache attempt chain."""

import uuid
from datetime import UTC, datetime

from llm_gateway.catalog import load_catalog
from llm_gateway.cost import compute_cost
from llm_gateway.demo.usage import usage_rows
from llm_gateway.tenants.models import Organization, Team


def test_recovery_chain_has_unbilled_failures_and_destination_priced_success() -> None:
    org = Organization(id=uuid.uuid4(), name="Fake synthetic org")
    team = Team(id=uuid.uuid4(), organization_id=org.id, name="Fake synthetic team")
    catalog = load_catalog()
    now = datetime(2026, 10, 1, 14, tzinfo=UTC)
    rows = usage_rows(org, [team], catalog, {team.id: ["abcdefghijkl"]}, now)
    assert {row.alias for row in rows if row.alias} <= set(catalog.aliases)
    assert set(catalog.aliases) <= {row.alias for row in rows if row.alias}
    recovered = next(row for row in rows if row.attempt == 3)
    attempts = sorted(
        (row for row in rows if row.request_id == recovered.request_id), key=lambda row: row.attempt
    )

    assert [row.attempt for row in attempts] == [1, 2, 3]
    assert [row.status_code for row in attempts] == [502, 502, 200]
    assert all(row.cost_status == "not_billed" and row.saved_usd is None for row in attempts[:2])
    assert recovered.provider == "deepseek"
    assert recovered.outcome == "success"
    destination = next(
        item
        for item in catalog.models
        if item.provider == recovered.provider and item.model == recovered.model
    )
    price = destination.at(now)
    assert price is not None
    assert recovered.cost_usd == compute_cost(price, 40000, 3000, 0)
    assert recovered.saved_usd is None
    assert attempts[0].created_at < attempts[1].created_at < attempts[2].created_at
