"""Policy views and conditional writes; enforcement remains in the repositories."""

from fastapi import APIRouter, Request

from llm_gateway.admin.api.auth import service
from llm_gateway.admin.api.models import GuardrailsBody, ModelsBody, ResidencyBody
from llm_gateway.catalog import load_catalog
from llm_gateway.guardrails.policy import DEFAULTS, DETECTORS
from llm_gateway.routing.policy import ModelPolicy

router = APIRouter()


@router.get("/orgs/{org}/model-policy")
async def get_models(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    _, policy, versions = await service(request).policy_snapshot(org, team)
    return {
        "overrides": {
            "organization": list(policy.organization) if policy.organization is not None else None,
            "team": list(policy.team) if policy.team is not None else None,
        },
        "effective": effective_models(policy),
        "version": versions["model_patterns"],
    }


@router.put("/orgs/{org}/model-policy")
async def set_models(
    request: Request, org: str, body: ModelsBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_models(org, team, body.allow, request.headers.get("if-match"))
    return {"updated": True}


@router.delete("/orgs/{org}/model-policy")
async def clear_models(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    await service(request).set_models(org, team, None, request.headers.get("if-match"))
    return {"cleared": True}


@router.put("/orgs/{org}/guardrails")
async def set_guardrails(
    request: Request, org: str, body: GuardrailsBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(
        org,
        team,
        residency=False,
        values=body.actions,
        expected_version=request.headers.get("if-match"),
    )
    return {"updated": True}


@router.get("/orgs/{org}/guardrails")
async def get_guardrails(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    guardrails, _, versions = await service(request).policy_snapshot(org, team)
    return {
        "overrides": {
            "organization": dict(guardrails.organization),
            "team": dict(guardrails.team),
        },
        "effective": {name: guardrails.action(name) for name in DETECTORS},
        "defaults": DEFAULTS,
        "version": versions["guardrail_actions"],
    }


@router.delete("/orgs/{org}/guardrails")
async def clear_guardrails(
    request: Request, org: str, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(
        org, team, residency=False, values=None, expected_version=request.headers.get("if-match")
    )
    return {"cleared": True}


@router.put("/orgs/{org}/residency")
async def set_residency(
    request: Request, org: str, body: ResidencyBody, team: str | None = None
) -> dict[str, object]:
    await service(request).set_policy(
        org,
        team,
        residency=True,
        values=body.regions,
        expected_version=request.headers.get("if-match"),
    )
    return {"updated": True}


@router.get("/orgs/{org}/residency")
async def get_residency(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    _, policy, versions = await service(request).policy_snapshot(org, team)
    return {
        "overrides": {
            "organization": list(policy.organization_regions)
            if policy.organization_regions is not None
            else None,
            "team": list(policy.team_regions) if policy.team_regions is not None else None,
        },
        "effective": {"regions": list(policy.regions), **effective_models(policy)},
        "version": versions["allowed_regions"],
    }


@router.delete("/orgs/{org}/residency")
async def clear_residency(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    await service(request).set_policy(
        org, team, residency=True, values=None, expected_version=request.headers.get("if-match")
    )
    return {"cleared": True}


def effective_models(policy: ModelPolicy) -> dict[str, object]:
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
    return {"models": models, "aliases": aliases}
