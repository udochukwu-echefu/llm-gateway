"""Limits and policy HTTP endpoints, with the shared service doing mutations."""

from fastapi import APIRouter, Request

from llm_gateway.admin_api.auth import service
from llm_gateway.admin_api.models import (
    BudgetBody,
    GuardrailsBody,
    LimitsBody,
    ModelsBody,
    ResidencyBody,
)
from llm_gateway.admin_limits import admin_defaults
from llm_gateway.catalog import load_catalog
from llm_gateway.guardrails.policy import DETECTORS
from llm_gateway.limits.configuration import resolve

router = APIRouter()


@router.get("/orgs/{org}/teams/{team}/limits")
async def get_limits(request: Request, org: str, team: str) -> dict[str, object]:
    _, overrides = await service(request).team_limits(org, team)
    effective = resolve(overrides, admin_defaults())
    return {
        "overrides": {
            "rpm": overrides.rpm,
            "tpm": overrides.tpm,
            "max_concurrency": overrides.max_concurrency,
        },
        "effective": {
            "rpm": effective.rpm,
            "tpm": effective.tpm,
            "max_concurrency": effective.max_concurrency,
        },
    }


@router.put("/orgs/{org}/teams/{team}/limits")
async def set_limits(request: Request, org: str, team: str, body: LimitsBody) -> dict[str, object]:
    await service(request).set_limits(
        org, team, rpm=body.rpm, tpm=body.tpm, max_concurrency=body.max_concurrency
    )
    return {"updated": True}


@router.delete("/orgs/{org}/teams/{team}/limits")
async def clear_limits(request: Request, org: str, team: str) -> dict[str, object]:
    await service(request).set_limits(org, team, clear=True)
    return {"cleared": True}


@router.put("/orgs/{org}/teams/{team}/budget")
async def set_budget(request: Request, org: str, team: str, body: BudgetBody) -> dict[str, object]:
    await service(request).set_limits(org, team, budget=body.usd, alert=body.alert_at)
    return {"updated": True, "usd": str(body.usd), "alert_at": str(body.alert_at)}


@router.get("/orgs/{org}/teams/{team}/budget")
async def get_budget(request: Request, org: str, team: str) -> dict[str, object]:
    _, overrides = await service(request).team_limits(org, team)
    effective = resolve(overrides, admin_defaults())
    return {
        "overrides": {
            "usd": str(overrides.monthly_budget_usd)
            if overrides.monthly_budget_usd is not None
            else None,
            "alert_at": str(overrides.alert_threshold)
            if overrides.alert_threshold is not None
            else None,
        },
        "effective": {
            "usd": str(effective.monthly_budget_usd),
            "alert_at": str(effective.alert_threshold),
        },
    }


@router.get("/orgs/{org}/model-policy")
async def get_models(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    _, policy = await service(request).policies(org, team)
    catalog = load_catalog()
    models = [
        f"{entry.provider}/{entry.model}"
        for entry in catalog.models
        if policy.allows(f"{entry.provider}/{entry.model}", entry.region)
    ]
    aliases = [
        name
        for name, alias in catalog.aliases.items()
        if any(
            policy.allows(target.model, catalog.region(target.model)) for target in alias.targets
        )
    ]
    return {
        "overrides": {
            "organization": list(policy.organization) if policy.organization is not None else None,
            "team": list(policy.team) if policy.team is not None else None,
        },
        "effective": {"models": models, "aliases": aliases},
    }


@router.put("/orgs/{org}/model-policy")
async def set_models(
    request: Request, org: str, body: ModelsBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_models(org, team, body.allow)
    return {"updated": True}


@router.delete("/orgs/{org}/model-policy")
async def clear_models(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    await service(request).set_models(org, team, None)
    return {"cleared": True}


@router.put("/orgs/{org}/guardrails")
async def set_guardrails(
    request: Request, org: str, body: GuardrailsBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(org, team, residency=False, values=body.actions)
    return {"updated": True}


@router.get("/orgs/{org}/guardrails")
async def get_guardrails(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    guardrails, _ = await service(request).policies(org, team)
    return {
        "overrides": {
            "organization": dict(guardrails.organization),
            "team": dict(guardrails.team),
        },
        "effective": {name: guardrails.action(name) for name in DETECTORS},
    }


@router.delete("/orgs/{org}/guardrails")
async def clear_guardrails(
    request: Request, org: str, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(org, team, residency=False, values=None)
    return {"cleared": True}


@router.put("/orgs/{org}/residency")
async def set_residency(
    request: Request, org: str, body: ResidencyBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(org, team, residency=True, values=body.regions)
    return {"updated": True}


@router.get("/orgs/{org}/residency")
async def get_residency(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    _, policy = await service(request).policies(org, team)
    return {
        "overrides": {
            "organization": list(policy.organization_regions)
            if policy.organization_regions is not None
            else None,
            "team": list(policy.team_regions) if policy.team_regions is not None else None,
        },
        "effective": {"regions": list(policy.regions)},
    }


@router.delete("/orgs/{org}/residency")
async def clear_residency(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    await service(request).set_policy(org, team, residency=True, values=None)
    return {"cleared": True}
