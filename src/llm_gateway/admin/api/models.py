"""Strict JSON contracts for administrative requests."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator, Field

from llm_gateway.schemas.common import RequestModel


class NameBody(RequestModel):
    name: str = Field(min_length=1, max_length=256)


class KeyBody(NameBody):
    expires_in_days: int | None = Field(default=None, gt=0)


class LimitsBody(RequestModel):
    rpm: int | None = Field(default=None, ge=0)
    tpm: int | None = Field(default=None, ge=0)
    max_concurrency: int | None = Field(default=None, ge=0)


def decimal_string(value: object) -> Decimal:
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError("Money must be a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal string") from exc


Money = Annotated[Decimal, BeforeValidator(decimal_string)]


class BudgetBody(RequestModel):
    usd: Money = Field(ge=0, le=Decimal("9223372.036854775807"), decimal_places=12)
    alert_at: Money = Field(default=Decimal("0.8"), gt=0, le=1)


class ModelsBody(RequestModel):
    allow: list[str]


class GuardrailsBody(RequestModel):
    actions: list[str]


class ResidencyBody(RequestModel):
    regions: list[str]
