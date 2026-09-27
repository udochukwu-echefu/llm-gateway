"""Catalogue-only alias declarations; targets are always concrete model IDs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, get_args

from pydantic import BaseModel, ConfigDict, Field

from llm_gateway.schemas.common import ProviderName

if TYPE_CHECKING:
    from llm_gateway.catalog import ModelPrice


class WeightedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model: str
    weight: int = Field(gt=0)


class Alias(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    targets: list[WeightedTarget] = Field(min_length=1)


def validate_aliases(aliases: dict[str, Alias], models: list[ModelPrice]) -> None:
    entries = {f"{entry.provider}/{entry.model}": entry for entry in models}
    for name, alias in aliases.items():
        if re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name) is None:
            raise ValueError("alias names must match ^[a-z][a-z0-9-]{0,31}$")
        if name in get_args(ProviderName):
            raise ValueError("alias cannot equal a provider name")
        if any(target.model not in entries for target in alias.targets):
            raise ValueError("alias target must be a concrete catalogued model")
        if len({entries[target.model].kind for target in alias.targets}) != 1:
            raise ValueError("alias targets must have the same kind")
        if len({target.model for target in alias.targets}) != len(alias.targets):
            raise ValueError("duplicate alias target")
