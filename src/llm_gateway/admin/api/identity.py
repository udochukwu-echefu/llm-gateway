"""Expose only the verified administrator identity, never credential material."""

from typing import cast

from fastapi import APIRouter, Request

from llm_gateway.admin.api.auth import AdminPrincipal, context
from llm_gateway.guardrails.policy import REGIONS
from llm_gateway.tenants.models import Organization

router = APIRouter()


@router.get("/me")
async def me(request: Request) -> dict[str, object]:
    principal = cast(AdminPrincipal, request.state.admin_principal)
    organization = None
    if principal.organization_id is not None:
        async with context(request).sessions() as session:
            org = await session.get(Organization, principal.organization_id)
        if org is not None:
            organization = {"id": str(org.id), "name": org.name}
    return {
        "key_id": principal.key_id,
        "name": principal.name,
        "role": principal.role,
        "organization": organization,
        "regions": list(REGIONS),
    }
