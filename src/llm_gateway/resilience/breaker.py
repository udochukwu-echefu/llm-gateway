"""A local fuse with synchronous admission so only one task can acquire a probe."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import structlog

from llm_gateway.observability.metrics import Metrics
from llm_gateway.observability.tracing import current
from llm_gateway.resilience.configuration import ResilienceSettings

log = structlog.get_logger("llm_gateway.resilience")


@dataclass(frozen=True)
class Permit:
    generation: int
    probe: bool = False


class CircuitBreaker:
    def __init__(
        self,
        provider: str,
        settings: ResilienceSettings,
        clock: Callable[[], float],
        metrics: Metrics | None = None,
    ) -> None:
        self.metrics = metrics
        if metrics is not None:
            metrics.circuit.labels(provider).set(0)
        self.provider = provider
        self.settings = settings
        self.clock = clock
        self.state = "closed"
        self.calls: deque[tuple[float, bool]] = deque()
        self.opened_at = 0.0
        self.generation = 0

    def acquire(self) -> Permit | None:
        if self.state == "open" and self.clock() - self.opened_at >= self.settings.breaker_open_s:
            self._transition("half_open")
            return Permit(self.generation, probe=True)
        if self.state != "closed":
            return None
        return Permit(self.generation)

    def finish(self, permit: Permit, failed: bool) -> None:
        if permit.generation != self.generation:
            return
        if permit.probe:
            self._transition("open" if failed else "closed")
            self.calls.clear()
            return
        self._expire()
        self.calls.append((self.clock(), failed))
        if len(self.calls) >= self.settings.breaker_min_calls and (
            sum(failed for _, failed in self.calls) / len(self.calls)
            >= self.settings.breaker_failure_ratio
        ):
            self._transition("open")

    def abandon(self, permit: Permit) -> None:
        # A cancelled probe proves nothing; reopen rather than leaving the fuse stuck.
        if permit.probe and permit.generation == self.generation:
            self._transition("open")

    def _expire(self) -> None:
        while self.calls and self.calls[0][0] <= self.clock() - self.settings.breaker_window_s:
            self.calls.popleft()

    def _transition(self, state: str) -> None:
        self._expire()
        self.state = state
        telemetry = current.get()
        metrics = self.metrics or (telemetry.metrics if telemetry else None)
        if metrics is not None:
            metrics.circuit.labels(self.provider).set(
                {"closed": 0, "half_open": 1, "open": 2}[state]
            )
        self.generation += 1
        if state == "open":
            self.opened_at = self.clock()
        event = {
            "open": "circuit_opened",
            "half_open": "circuit_half_open",
            "closed": "circuit_closed",
        }
        log.info(
            event[state],
            provider=self.provider,
            calls=len(self.calls),
            failures=sum(failed for _, failed in self.calls),
        )
