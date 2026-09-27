"""An optional team allowlist can only narrow the organization's allowlist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from llm_gateway.errors import GatewayError

if TYPE_CHECKING:
    from llm_gateway.catalog import Catalog


@dataclass(frozen=True)
class ModelPolicy:
    organization: tuple[str, ...] | None = None
    team: tuple[str, ...] | None = None

    def allows(self, model: str) -> bool:
        return _allows(self.organization, model) and _allows(self.team, model)

    def require(self, model: str) -> None:
        if not self.allows(model):
            raise denied(model)


def denied(model: str) -> GatewayError:
    return GatewayError(
        403,
        f"Model '{model}' is not allowed for this team.",
        type="invalid_request_error",
        code="model_not_allowed",
    )


def validate_patterns(patterns: list[str], catalog: Catalog) -> tuple[str, ...]:
    names = [f"{entry.provider}/{entry.model}" for entry in catalog.models]
    for pattern in patterns:
        provider, slash, model = pattern.partition("/")
        if (
            not slash
            or not provider
            or not model
            or ("*" in pattern and (model != "*" or "*" in provider))
            or not any(_matches(pattern, name) for name in names)
        ):
            raise ValueError(f"Model pattern '{pattern}' must match a catalogued model")
    return tuple(dict.fromkeys(patterns))


def _allows(patterns: tuple[str, ...] | None, model: str) -> bool:
    return patterns is None or any(_matches(pattern, model) for pattern in patterns)


def _matches(pattern: str, model: str) -> bool:
    return model == pattern or (pattern.endswith("/*") and model.startswith(pattern[:-1]))
