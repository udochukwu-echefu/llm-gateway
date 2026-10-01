"""Configuration reads expose both saved overrides and current effective rules."""

import pytest

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_limits_and_budget_reads_show_overrides_and_defaults(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    base = f"/admin/v1/orgs/{harness.org}/teams/team"
    headers = harness.headers(harness.org_key)

    initial_limits = await harness.client.get(f"{base}/limits", headers=headers)
    initial_budget = await harness.client.get(f"{base}/budget", headers=headers)
    await harness.client.put(f"{base}/limits", json={"rpm": 7}, headers=headers)
    await harness.client.put(
        f"{base}/budget", json={"usd": "1.250000000001", "alert_at": "0.5"}, headers=headers
    )
    limits = await harness.client.get(f"{base}/limits", headers=headers)
    budget = await harness.client.get(f"{base}/budget", headers=headers)

    assert initial_limits.status_code == initial_budget.status_code == 200
    assert initial_limits.json()["overrides"] == {
        "rpm": None,
        "tpm": None,
        "max_concurrency": None,
    }
    assert isinstance(initial_limits.json()["effective"]["rpm"], int)
    assert initial_budget.json()["overrides"] == {"usd": None, "alert_at": None}
    assert isinstance(initial_budget.json()["effective"]["usd"], str)
    assert limits.json()["overrides"]["rpm"] == limits.json()["effective"]["rpm"] == 7
    assert limits.json()["overrides"]["tpm"] is None
    assert budget.json() == {
        "display_usd": "1.250000000001",
        "overrides": {"usd": "1.250000000001", "alert_at": "0.500"},
        "effective": {"usd": "1.250000000001", "alert_at": "0.500"},
    }


async def test_policy_reads_show_org_and_team_overrides_and_effective_values(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    base = f"/admin/v1/orgs/{harness.org}"
    headers = harness.headers(harness.org_key)
    await harness.client.put(f"{base}/model-policy", json={"allow": ["groq/*"]}, headers=headers)
    await harness.client.put(f"{base}/model-policy?team=team", json={"allow": []}, headers=headers)
    await harness.client.put(
        f"{base}/guardrails", json={"actions": ["email=redact"]}, headers=headers
    )
    await harness.client.put(
        f"{base}/guardrails?team=team", json={"actions": ["phone=block"]}, headers=headers
    )
    await harness.client.put(f"{base}/residency", json={"regions": ["us", "eu"]}, headers=headers)
    await harness.client.put(
        f"{base}/residency?team=team", json={"regions": ["us"]}, headers=headers
    )

    models = await harness.client.get(f"{base}/model-policy?team=team", headers=headers)
    guardrails = await harness.client.get(f"{base}/guardrails?team=team", headers=headers)
    residency = await harness.client.get(f"{base}/residency?team=team", headers=headers)

    assert models.status_code == guardrails.status_code == residency.status_code == 200
    assert models.json()["overrides"] == {"organization": ["groq/*"], "team": []}
    assert models.json()["effective"] == {"models": [], "aliases": []}
    assert guardrails.json()["overrides"] == {
        "organization": {"email": "redact"},
        "team": {"phone": "block"},
    }
    assert guardrails.json()["effective"]["email"] == "redact"
    assert guardrails.json()["effective"]["phone"] == "block"
    assert residency.json()["overrides"] == {"organization": ["us", "eu"], "team": ["us"]}
    assert len(residency.json()["version"]) == 64
    assert residency.json()["effective"] == {
        "regions": ["us"],
        "models": [],
        "aliases": [],
    }


async def test_residency_accepts_sg_and_lists_it_in_validation_errors(
    admin_harness: AdminHarness,
) -> None:
    harness = admin_harness
    path = f"/admin/v1/orgs/{harness.org}/residency"
    headers = harness.headers(harness.org_key)

    response = await harness.client.put(path, json={"regions": ["sg"]}, headers=headers)
    saved = await harness.client.get(path, headers=headers)
    invalid = await harness.client.put(path, json={"regions": ["bad"]}, headers=headers)

    assert response.status_code == 200
    assert saved.json()["effective"]["regions"] == ["sg"]
    assert invalid.status_code == 400
    assert "sg" in invalid.json()["error"]["message"]
