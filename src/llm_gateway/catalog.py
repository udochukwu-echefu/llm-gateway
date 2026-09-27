"""Reviewed model allowlist and decimal prices, loaded before accepting traffic."""

import tomllib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from llm_gateway.schemas.common import ProviderName


class PricePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    effective_from: date
    input_price: Decimal = Field(ge=0)
    cached_input_price: Decimal | None = Field(default=None, ge=0)
    output_price: Decimal | None = Field(default=None, ge=0)
    currency: Literal["USD"] = "USD"
    source_url: HttpUrl
    checked_on: date

    @field_validator("input_price", "cached_input_price", "output_price", mode="before")
    @classmethod
    def _decimal_from_toml(cls, value: object) -> object:
        if isinstance(value, str):
            return Decimal(value)
        return value

    @model_validator(mode="after")
    def _valid_cache_price(self) -> Self:
        if self.cached_input_price is not None and self.cached_input_price > self.input_price:
            raise ValueError("cached price cannot exceed input price")
        return self


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: ProviderName
    model: str = Field(min_length=1)
    kind: Literal["chat", "embedding"]
    periods: list[PricePeriod] = Field(min_length=1)
    fallbacks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_periods(self) -> Self:
        dates = [period.effective_from for period in self.periods]
        if dates != sorted(set(dates)):
            raise ValueError("price periods must have strictly increasing unique dates")
        if any(
            (period.output_price is None) != (self.kind == "embedding") for period in self.periods
        ):
            raise ValueError("chat needs an output price; embeddings must not have one")
        return self

    def at(self, requested_at: datetime) -> PricePeriod | None:
        """Periods start at midnight UTC; future-only models are not yet available."""
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("request timestamp must be timezone-aware")
        day = requested_at.astimezone(UTC).date()
        return next(
            (period for period in reversed(self.periods) if period.effective_from <= day), None
        )


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: str = Field(min_length=1)
    models: list[ModelPrice]

    @model_validator(mode="after")
    def _unique_models(self) -> Self:
        keys = [(entry.provider, entry.model) for entry in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate provider/model in catalogue")
        return self

    @model_validator(mode="after")
    def _valid_fallbacks(self) -> Self:
        entries = {f"{entry.provider}/{entry.model}": entry for entry in self.models}
        for name, entry in entries.items():
            for target in entry.fallbacks:
                if target == name:
                    raise ValueError("fallback cannot reference itself")
                if target not in entries:
                    raise ValueError("unknown fallback target")
                if entries[target].kind != entry.kind:
                    raise ValueError("fallback must have the same kind")
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError("fallback cycle")
            if name in visited:
                return
            visiting.add(name)
            for target in entries[name].fallbacks:
                visit(target)
            visiting.remove(name)
            visited.add(name)

        for name in entries:
            visit(name)
        return self

    def find(self, provider: ProviderName, model: str, kind: str) -> ModelPrice | None:
        return next(
            (
                e
                for e in self.models
                if e.provider == provider and e.model == model and e.kind == kind
            ),
            None,
        )


DEFAULT_CATALOG = Path("catalog/models.toml")


def load_catalog(path: Path = DEFAULT_CATALOG) -> Catalog:
    with path.open("rb") as source:
        return Catalog.model_validate(tomllib.load(source))
