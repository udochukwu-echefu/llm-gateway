"""Once opened, a stream never re-enters retry or fallback policy."""

import asyncio
from collections.abc import AsyncIterator, Callable

from llm_gateway.errors import GatewayError
from llm_gateway.observability.attempt import AttemptObservation
from llm_gateway.providers.base import ChatStream
from llm_gateway.resilience.breaker import CircuitBreaker, Permit
from llm_gateway.resilience.retry import breaker_failure
from llm_gateway.schemas.chat import ChatCompletionChunk
from llm_gateway.usage.record import UsageEvent


def deadline_error() -> GatewayError:
    return GatewayError(
        504,
        "The request deadline expired.",
        type="upstream_error",
        code="upstream_timeout",
        transport_kind="DeadlineExceeded",
    )


class DeadlineStream:
    def __init__(
        self,
        stream: ChatStream,
        deadline: float,
        clock: Callable[[], float],
        breaker: CircuitBreaker,
        permit: Permit,
        event: UsageEvent,
        started: float,
        observation: AttemptObservation,
    ) -> None:
        self.observation = observation
        self.event, self.started = event, started
        self.stream = stream
        self.deadline = deadline
        self.clock = clock
        self.breaker = breaker
        self.permit = permit
        self.settled = False

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]:
        return self._chunks()

    async def aclose(self) -> None:
        self.event.duration_ms = round((self.clock() - self.started) * 1000, 2)
        if not self.settled:
            if self.event.outcome == "success":
                self.event.outcome = "client_disconnected"
                self.event.status_code = 499
            self.breaker.abandon(self.permit)
            self.settled = True
        try:
            await self.stream.aclose()
        finally:
            self.observation.finish()

    async def _chunks(self) -> AsyncIterator[ChatCompletionChunk]:
        iterator = self.stream.__aiter__()
        try:
            try:
                async with asyncio.timeout(max(0, self.deadline - self.clock())):
                    first = await self.observation.wait(anext(iterator))
            except TimeoutError:
                raise deadline_error() from None
            self.event.ttfb_ms = round((self.clock() - self.started) * 1000, 2)
            self.observation.span.set_attribute(
                "gen_ai.response.model", first.model.split("/", 1)[-1]
            )
            yield first
            while True:
                yield await self.observation.wait(anext(iterator))
        except StopAsyncIteration:
            pass
        except GatewayError as exc:
            self.event.outcome, self.event.status_code = "stream_error", exc.status_code
            self.breaker.finish(self.permit, breaker_failure(exc))
            self.settled = True
            raise
        except BaseException as exc:
            self.event.outcome = (
                "client_disconnected"
                if isinstance(exc, (asyncio.CancelledError, GeneratorExit))
                else "gateway_error"
            )
            self.event.status_code = 499 if self.event.outcome == "client_disconnected" else 500
            self.breaker.abandon(self.permit)
            self.settled = True
            raise
        else:
            self.breaker.finish(self.permit, False)
            self.settled = True
            return
        self.breaker.finish(self.permit, False)
        self.settled = True
