"""One policy entry point for endpoints; adapters remain unaware of recovery."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

from llm_gateway.catalog import Catalog
from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import ChatStream
from llm_gateway.providers.registry import ProviderRegistry
from llm_gateway.resilience.attempt import ModelResult, run_attempt
from llm_gateway.resilience.breaker import CircuitBreaker
from llm_gateway.resilience.configuration import ResilienceSettings
from llm_gateway.resilience.execution import Execution
from llm_gateway.resilience.fallback import ModelRequest, Target, resolve_target, unavailable
from llm_gateway.resilience.retry import RetryBudget, retry_delay, retryable
from llm_gateway.resilience.stream import deadline_error
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse


class ResilienceService:
    def __init__(
        self,
        registry: ProviderRegistry,
        catalog: Catalog,
        settings: ResilienceSettings,
        *,
        clock: Callable[[], float] = time.perf_counter,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: Callable[[], float] = random.random,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.registry, self.catalog, self.settings = registry, catalog, settings
        self.clock, self.sleep, self.random, self.wall_clock = (
            clock,
            sleep,
            random_source,
            wall_clock,
        )
        self.breakers = {name: CircuitBreaker(name, settings, clock) for name in registry.adapters}
        self.budgets = {name: RetryBudget(settings, clock) for name in registry.adapters}

    async def execute_chat(
        self, request: ChatCompletionRequest, execution: Execution
    ) -> ChatCompletion | ChatStream:
        result = await self._execute(request, execution)
        if isinstance(result, EmbeddingResponse):
            raise RuntimeError("chat returned an embedding")
        return result

    async def execute_embedding(
        self, request: EmbeddingRequest, execution: Execution
    ) -> EmbeddingResponse:
        result = await self._execute(request, execution)
        if not isinstance(result, EmbeddingResponse):
            raise RuntimeError("embedding returned a chat")
        return result

    async def _execute(self, request: ModelRequest, execution: Execution) -> ModelResult:
        deadline = self.clock() + self.settings.deadline_s
        target = resolve_target(
            request.model, request, self.registry, self.catalog, execution.requested_at
        )
        names = [request.model, *(target.price.fallbacks if execution.allow_fallback else [])]
        error = unavailable()
        for index, name in enumerate(names):
            if self.clock() >= deadline:
                error = deadline_error()
                break
            if index:
                try:
                    target = resolve_target(
                        name, request, self.registry, self.catalog, execution.requested_at
                    )
                except GatewayError:
                    continue
            try:
                return await self._target(request, target, execution, deadline)
            except GatewayError as exc:
                error = exc
                if exc.code != "provider_unavailable" and not retryable(exc, self.settings):
                    break
        error.headers.update(execution.headers)
        raise error

    async def _target(
        self, request: ModelRequest, target: Target, execution: Execution, deadline: float
    ) -> ModelResult:
        breaker = self.breakers[target.adapter.name]
        budget = self.budgets[target.adapter.name]
        for retry in range(self.settings.max_retries + 1):
            if self.clock() >= deadline:
                raise deadline_error()
            permit = breaker.acquire()
            if permit is None:
                raise unavailable()
            if retry == 0:
                budget.first()
            try:
                return await run_attempt(
                    request, target, execution, self.catalog, breaker, permit, deadline, self.clock
                )
            except GatewayError as exc:
                if retry == self.settings.max_retries or not retryable(exc, self.settings):
                    raise
                delay = retry_delay(exc, retry, self.settings, self.random, self.wall_clock)
                if delay is None or delay >= deadline - self.clock() or not budget.take():
                    raise
                try:
                    async with asyncio.timeout(max(0, deadline - self.clock())):
                        await self.sleep(delay)
                except TimeoutError:
                    raise deadline_error() from None
        raise RuntimeError("retry loop must return or raise")
