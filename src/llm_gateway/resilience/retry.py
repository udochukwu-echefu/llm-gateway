"""Bound amplification before adding load to an already unhealthy provider."""

import time
from collections import deque
from collections.abc import Callable
from datetime import UTC
from email.utils import parsedate_to_datetime

from llm_gateway.errors import GatewayError
from llm_gateway.resilience.configuration import ResilienceSettings


class RetryBudget:
    def __init__(self, settings: ResilienceSettings, clock: Callable[[], float]) -> None:
        self.settings = settings
        self.clock = clock
        self.firsts: deque[float] = deque()
        self.retries: deque[float] = deque()

    def first(self) -> None:
        self._expire()
        self.firsts.append(self.clock())

    def take(self) -> bool:
        self._expire()
        if len(self.retries) + 1 > max(
            self.settings.retry_budget_min_per_window,
            len(self.firsts) * self.settings.retry_budget_ratio,
        ):
            return False
        self.retries.append(self.clock())
        return True

    def _expire(self) -> None:
        boundary = self.clock() - self.settings.retry_window_s
        for calls in (self.firsts, self.retries):
            while calls and calls[0] <= boundary:
                calls.popleft()


def retryable(error: GatewayError, settings: ResilienceSettings) -> bool:
    if error.upstream_status is not None:
        return error.upstream_status in {429, 500, 502, 503, 504, 529}
    return error.transport_kind in {"ConnectError", "ConnectTimeout", "PoolTimeout"} or (
        settings.retry_read_timeouts and error.transport_kind == "ReadTimeout"
    )


def breaker_failure(error: GatewayError) -> bool:
    if error.upstream_status is not None:
        return error.upstream_status == 429 or error.upstream_status >= 500
    return error.transport_kind in {
        "ConnectError",
        "ConnectTimeout",
        "PoolTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "DeadlineExceeded",
    }


def retry_delay(
    error: GatewayError,
    retry: int,
    settings: ResilienceSettings,
    random: Callable[[], float],
    wall_clock: Callable[[], float] = time.time,
) -> float | None:
    value = error.headers.get("retry-after")
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                delay = when.replace(tzinfo=when.tzinfo or UTC).timestamp() - wall_clock()
            except (ValueError, TypeError, OverflowError):
                delay = -1
        if delay > settings.retry_cap_s:
            return None
        if delay >= 0:
            return delay
    return random() * min(settings.retry_cap_s, settings.retry_base_s * 2**retry)
