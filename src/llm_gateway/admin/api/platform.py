"""Platform-only configuration and replica-labelled provider health."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from llm_gateway.admin.api.auth import context, service
from llm_gateway.admin.service.platform_settings import provider_settings, public_settings
from llm_gateway.usage.repository import UsageRow

router = APIRouter()


@router.get("/settings")
async def settings(request: Request) -> dict[str, object]:
    service(request).require_platform(read_only=True)
    if request.query_params:
        raise ValueError("Invalid settings query")
    configured = context(request).settings
    if configured is None:
        raise ValueError("Runtime configuration unavailable")
    return public_settings(configured)


@router.get("/providers")
async def providers(request: Request) -> dict[str, object]:
    service(request).require_platform(read_only=True)
    if request.query_params:
        raise ValueError("Invalid providers query")
    ctx = context(request)
    if ctx.settings is None:
        raise ValueError("Runtime configuration unavailable")
    result = provider_settings(ctx.settings)
    now = datetime.now(UTC)
    async with ctx.sessions() as session:
        for provider in result:
            provider["circuit_breaker"] = ctx.breaker_states().get(str(provider["provider"]))
            for label, delta in (("15m", timedelta(minutes=15)), ("24h", timedelta(hours=24))):
                count = func.count()
                row = (
                    (
                        await session.execute(
                            select(
                                count.label("attempts"),
                                (
                                    func.count().filter(UsageRow.status_code >= 400)
                                    * 1.0
                                    / func.nullif(count, 0)
                                ).label("error_rate"),
                                func.percentile_cont(0.95)
                                .within_group(UsageRow.duration_ms)
                                .label("p95_ms"),
                            ).where(
                                UsageRow.provider == provider["provider"],
                                UsageRow.created_at >= now - delta,
                                UsageRow.created_at <= now,
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                provider[label] = {
                    **row,
                    "p95_ms": round(row["p95_ms"], 1) if row["p95_ms"] is not None else None,
                }
    return {"data": result, "circuit_scope": "this replica"}
