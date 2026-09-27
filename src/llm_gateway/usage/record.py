"""Only metadata crosses the accounting boundary; no request or response bodies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from llm_gateway.catalog import Catalog, ModelPrice, PricePeriod
from llm_gateway.cost import compute_cost
from llm_gateway.schemas.chat import Usage
from llm_gateway.schemas.embeddings import EmbeddingUsage

if TYPE_CHECKING:
    from llm_gateway.tenants.auth import Principal

Outcome = Literal[
    "success", "upstream_error", "client_disconnected", "stream_error", "gateway_error", "cache_hit"
]
CostStatus = Literal["priced", "usage_missing", "stream_incomplete", "not_billed", "cached"]


@dataclass(frozen=True)
class UsageRecord:
    id: uuid.UUID
    request_id: str
    created_at: datetime
    organization_id: uuid.UUID
    team_id: uuid.UUID
    key_id: str
    provider: str
    model: str
    endpoint: Literal["chat", "embeddings"]
    stream: bool
    status_code: int
    outcome: Outcome
    cost_status: CostStatus
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None
    cost_usd: Decimal | None
    catalog_version: str
    duration_ms: float | None
    ttfb_ms: float | None
    attempt: int = 1
    fallback_from: str | None = None
    alias: str | None = None
    saved_usd: Decimal | None = None
    redaction_count: int | None = None


class UsageEvent:
    """One provider-bound call; finalize once the last response byte/disconnect is known."""

    def __init__(
        self,
        principal: Principal,
        request_id: str,
        price: ModelPrice,
        catalog: Catalog,
        endpoint: Literal["chat", "embeddings"],
        stream: bool,
        requested_at: datetime | None = None,
        attempt: int = 1,
        fallback_from: str | None = None,
        alias: str | None = None,
    ) -> None:
        self.alias = alias
        self.attempt = attempt
        self.fallback_from = fallback_from
        self.duration_ms: float | None = None
        self.ttfb_ms: float | None = None
        self.principal = principal
        self.request_id = request_id
        self.price = price
        self.requested_at = requested_at if requested_at is not None else datetime.now(UTC)
        period = price.at(self.requested_at)
        if period is None:
            raise ValueError("model has no price at request timestamp")
        self.period: PricePeriod = period
        self.catalog = catalog
        self.endpoint: Literal["chat", "embeddings"] = endpoint
        self.stream = stream
        self.usage: Usage | EmbeddingUsage | None = None
        self.outcome: Outcome = "success"
        self.status_code = 200
        self.finished = False
        self.sent = False
        self.provider_rejected = False
        self.connect_failed = False

    def finish(self, duration_ms: float | None, ttfb_ms: float | None) -> UsageRecord:
        usage = self.usage
        prompt = usage.prompt_tokens if usage is not None else None
        completion = usage.completion_tokens if isinstance(usage, Usage) else None
        cached = (
            usage.prompt_tokens_details.cached_tokens
            if isinstance(usage, Usage) and usage.prompt_tokens_details
            else None
        )
        reasoning = (
            usage.completion_tokens_details.reasoning_tokens
            if isinstance(usage, Usage) and usage.completion_tokens_details
            else None
        )
        cost_status: CostStatus = "priced" if usage is not None else "usage_missing"
        cost: Decimal | None = None
        if usage is not None:
            try:
                cost = compute_cost(self.period, prompt or 0, completion or 0, cached or 0)
            except ValueError:
                cost_status = "usage_missing"
        if self.outcome == "client_disconnected" and usage is None:
            cost_status, cost = "stream_incomplete", None
        elif (
            usage is None
            and self.outcome == "upstream_error"
            and (self.provider_rejected or self.connect_failed)
        ):
            cost_status, cost = "not_billed", Decimal(0)
        return UsageRecord(
            uuid.uuid4(),
            self.request_id,
            self.requested_at,
            self.principal.organization_id,
            self.principal.team_id,
            self.principal.key_id,
            self.price.provider,
            self.price.model,
            self.endpoint,
            self.stream,
            self.status_code,
            self.outcome,
            cost_status,
            prompt,
            completion,
            cached,
            reasoning,
            cost,
            self.catalog.version,
            self.duration_ms if self.duration_ms is not None else duration_ms,
            self.ttfb_ms if self.duration_ms is not None else ttfb_ms,
            self.attempt,
            self.fallback_from,
            self.alias,
        )
