"""Resolve nullable team overrides against global defaults; zero means unlimited."""

from dataclasses import dataclass
from decimal import Decimal

from llm_gateway.config import LimitsSettings


@dataclass(frozen=True)
class LimitOverrides:
    rpm: int | None = None
    tpm: int | None = None
    max_concurrency: int | None = None
    monthly_budget_usd: Decimal | None = None
    alert_threshold: Decimal | None = None


@dataclass(frozen=True)
class EffectiveLimits:
    rpm: int
    tpm: int
    max_concurrency: int
    monthly_budget_usd: Decimal
    alert_threshold: Decimal


def resolve(override: LimitOverrides, defaults: LimitsSettings) -> EffectiveLimits:
    return EffectiveLimits(
        defaults.default_rpm if override.rpm is None else override.rpm,
        defaults.default_tpm if override.tpm is None else override.tpm,
        defaults.default_max_concurrency
        if override.max_concurrency is None
        else override.max_concurrency,
        defaults.default_monthly_budget_usd
        if override.monthly_budget_usd is None
        else override.monthly_budget_usd,
        defaults.default_alert_threshold
        if override.alert_threshold is None
        else override.alert_threshold,
    )
