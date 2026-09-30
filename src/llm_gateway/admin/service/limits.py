"""Present team limit configuration and live counters without Python object reprs."""

import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from llm_gateway.config import LimitsSettings
from llm_gateway.limits.configuration import EffectiveLimits, LimitOverrides, resolve
from llm_gateway.limits.service import PICOS, LimitService


@dataclass(frozen=True)
class LiveLimits:
    spent_picos: int
    requests_remaining: int
    tokens_remaining: int
    active_leases: int


async def read_live_limits(
    service: LimitService,
    team_id: uuid.UUID,
    limits: EffectiveLimits,
) -> LiveLimits:
    now = datetime.now(UTC)
    budget = await service.check_budget(team_id, limits, now)
    requests = await service.window(str(team_id), "requests", limits.rpm, 0, False)
    tokens = await service.window(str(team_id), "tokens", limits.tpm, 0, False)
    active = cast(int, await service.client.zcount(f"lgw:leases:{team_id}", time.time(), "+inf"))
    return LiveLimits(budget[1], requests[1], tokens[1], active)


def admin_defaults() -> LimitsSettings:
    base = LimitsSettings()
    return LimitsSettings.model_validate(
        {
            name: os.environ.get(f"GATEWAY_LIMITS__{name.upper()}", getattr(base, name))
            for name in LimitsSettings.model_fields
        }
    )


def render_limits(
    org: str,
    team: str,
    overrides: LimitOverrides,
    defaults: LimitsSettings,
    live: LiveLimits | None,
) -> str:
    effective = resolve(overrides, defaults)
    rows = [
        _row("RPM", effective.rpm, overrides.rpm),
        _row("TPM", effective.tpm, overrides.tpm),
        _row("Max concurrency", effective.max_concurrency, overrides.max_concurrency),
        _row(
            "Monthly budget",
            effective.monthly_budget_usd,
            overrides.monthly_budget_usd,
            currency=True,
        ),
        (
            "Alert threshold",
            f"{(effective.alert_threshold * 100).normalize():f}%",
            "override" if overrides.alert_threshold is not None else "default",
        ),
    ]
    spend = "unavailable"
    if live is not None:
        amount = Decimal(live.spent_picos) / PICOS
        percent = (
            f" ({amount / effective.monthly_budget_usd * 100:.2f}%)"
            if effective.monthly_budget_usd
            else ""
        )
        spend = f"${amount:.12f}{percent}"
    rows.extend(
        [
            ("Spend this month", spend, "live" if live is not None else "-"),
            (
                "Requests remaining",
                _remaining(live.requests_remaining, effective.rpm) if live else "unavailable",
                "live" if live else "-",
            ),
            (
                "Tokens remaining",
                _remaining(live.tokens_remaining, effective.tpm) if live else "unavailable",
                "live" if live else "-",
            ),
            (
                "Active leases",
                str(live.active_leases) if live else "unavailable",
                "live" if live else "-",
            ),
        ]
    )
    width = max(len(value) for _, value, _ in rows)
    lines = [f"Team: {org} / {team}", f"{'Limit':<22} {'Value':<{width}}  Source"]
    lines.extend(f"{label:<22} {value:<{width}}  {source}" for label, value, source in rows)
    lines.append("Changes take effect within the verified-key cache TTL.")
    return "\n".join(lines)


def _row(
    label: str,
    effective: int | Decimal,
    override: int | Decimal | None,
    *,
    currency: bool = False,
) -> tuple[str, str, str]:
    if effective == 0:
        return label, "unlimited", "unlimited"
    value = f"${effective:f}" if currency else str(effective)
    return label, value, "override" if override is not None else "default"


def _remaining(value: int, limit: int) -> str:
    return "unlimited" if limit == 0 else str(value)
