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

router = APIRouter()


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


@router.delete("/orgs/{org}/residency")
async def clear_residency(request: Request, org: str, team: str | None = None) -> dict[str, object]:
    await service(request).set_policy(org, team, residency=True, values=None)
    return {"cleared": True}
