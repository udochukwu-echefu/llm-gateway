"""Limits and budgets delegate mutations to the shared admin service."""

from fastapi import APIRouter, Request

from llm_gateway.admin.api.auth import service
from llm_gateway.admin.api.models import (
    BudgetBody,
    LimitsBody,
)
from llm_gateway.admin.service.limits import admin_defaults
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
    return {"updated": True, "usd": format(body.usd, "f"), "alert_at": format(body.alert_at, "f")}


@router.get("/orgs/{org}/teams/{team}/budget")
async def get_budget(request: Request, org: str, team: str) -> dict[str, object]:
    _, overrides = await service(request).team_limits(org, team)
    effective = resolve(overrides, admin_defaults())
    return {
        "overrides": {
            "usd": format(overrides.monthly_budget_usd, "f")
            if overrides.monthly_budget_usd is not None
            else None,
            "alert_at": format(overrides.alert_threshold, "f")
            if overrides.alert_threshold is not None
            else None,
        },
        "effective": {
            "usd": format(effective.monthly_budget_usd, "f"),
            "alert_at": format(effective.alert_threshold, "f"),
        },
    }
