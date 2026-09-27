"""Filter permissions before drawing a weighted, concrete destination."""

import random
from collections.abc import Callable, Collection
from datetime import datetime

from llm_gateway.catalog import Catalog
from llm_gateway.errors import GatewayError
from llm_gateway.routing.aliases import WeightedTarget
from llm_gateway.routing.policy import ModelPolicy, denied


def available_models(catalog: Catalog, configured: Collection[str], now: datetime) -> set[str]:
    return {
        f"{entry.provider}/{entry.model}"
        for entry in catalog.models
        if entry.provider in configured and entry.at(now) is not None
    }


def visible_aliases(catalog: Catalog, policy: ModelPolicy, available: set[str]) -> list[str]:
    return [
        name
        for name, alias in catalog.aliases.items()
        if any(
            target.model in available and policy.allows(target.model, catalog.region(target.model))
            for target in alias.targets
        )
    ]


def resolve_model(
    name: str,
    catalog: Catalog,
    policy: ModelPolicy,
    available: set[str],
    random_source: Callable[[], float] = random.random,
) -> tuple[str, str | None]:
    if "/" in name:
        policy.require(name, catalog.region(name))
        return name, None
    alias = catalog.aliases.get(name)
    if alias is None:
        choices = ", ".join(visible_aliases(catalog, policy, available)) or "none"
        raise GatewayError(
            404,
            f"Unknown model alias '{name}'. Available aliases: {choices}.",
            type="invalid_request_error",
            code="model_not_found",
        )
    allowed = [
        target
        for target in alias.targets
        if policy.allows(target.model, catalog.region(target.model))
    ]
    if not allowed:
        raise denied(name)
    targets = [target for target in allowed if target.model in available]
    if not targets:
        raise GatewayError(
            404,
            f"Alias '{name}' has no available model targets.",
            type="invalid_request_error",
            code="model_not_found",
        )
    concrete = _choose(targets, random_source)
    policy.require(concrete, catalog.region(concrete))
    return concrete, name


def _choose(targets: list[WeightedTarget], random_source: Callable[[], float]) -> str:
    draw = random_source() * sum(target.weight for target in targets)
    for target in targets:
        draw -= target.weight
        if draw < 0:
            return target.model
    raise ValueError("routing random source must return a value in [0, 1)")
