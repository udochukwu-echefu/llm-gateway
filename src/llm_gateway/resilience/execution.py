"""Request-local metadata; shared between policy and response finalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_gateway.tenants.auth import Principal
from llm_gateway.usage.record import UsageEvent


@dataclass
class Execution:
    principal: Principal
    request_id: str
    requested_model: str
    allow_fallback: bool = True
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    alias: str | None = None
    events: list[UsageEvent] = field(default_factory=list[UsageEvent])

    @property
    def headers(self) -> dict[str, str]:
        headers = {"x-lgw-alias": self.alias} if self.alias is not None else {}
        attempts = sum(event.sent for event in self.events)
        fallback = any(event.sent and event.fallback_from for event in self.events)
        if attempts <= 1 and not fallback:
            return headers
        headers.update(
            {"x-lgw-fallback-from": self.requested_model, "x-lgw-attempts": str(attempts)}
        )
        return headers
