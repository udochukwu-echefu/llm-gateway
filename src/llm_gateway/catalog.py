"""Reviewed model allowlist and decimal prices, loaded before accepting traffic."""

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from llm_gateway.schemas.common import ProviderName


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: ProviderName
    model: str = Field(min_length=1)
    kind: Literal["chat", "embedding"]
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
    def _consistent_prices(self) -> Self:
        if (self.output_price is None) != (self.kind == "embedding"):
            raise ValueError("chat needs an output price; embeddings must not have one")
        if self.cached_input_price is not None and self.cached_input_price > self.input_price:
            raise ValueError("cached price cannot exceed input price")
        return self


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
