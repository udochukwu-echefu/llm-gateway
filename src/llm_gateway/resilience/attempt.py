"""One network operation owns one receipt and one breaker observation."""

import asyncio
from collections.abc import Callable

from llm_gateway.catalog import Catalog
from llm_gateway.context import annotate
from llm_gateway.errors import GatewayError
from llm_gateway.observability.attempt import AttemptObservation
from llm_gateway.providers.base import ChatStream
from llm_gateway.resilience.breaker import CircuitBreaker, Permit
from llm_gateway.resilience.execution import Execution
from llm_gateway.resilience.fallback import ModelRequest, Target
from llm_gateway.resilience.retry import breaker_failure
from llm_gateway.resilience.stream import DeadlineStream, deadline_error
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest
from llm_gateway.schemas.embeddings import EmbeddingResponse
from llm_gateway.usage.binding import bind, unbind
from llm_gateway.usage.record import UsageEvent

ModelResult = ChatCompletion | EmbeddingResponse | ChatStream


async def run_attempt(
    request: ModelRequest,
    target: Target,
    execution: Execution,
    catalog: Catalog,
    breaker: CircuitBreaker,
    permit: Permit,
    deadline: float,
    clock: Callable[[], float],
    retry: bool = False,
) -> ModelResult:
    event = _new_event(request, target, execution, catalog)
    execution.events.append(event)
    annotate(provider=target.adapter.name, model=f"{target.adapter.name}/{target.model}")
    token = bind(event)
    started = clock()
    observation = AttemptObservation(event, retry)
    streaming = False
    try:
        result = await observation.wait(_call(request, target, deadline - clock()))
    except GatewayError as exc:
        event.outcome, event.status_code = "upstream_error", exc.status_code
        breaker.finish(permit, breaker_failure(exc))
        raise
    except BaseException as exc:
        event.outcome = (
            "client_disconnected" if isinstance(exc, asyncio.CancelledError) else "gateway_error"
        )
        event.status_code = 499 if isinstance(exc, asyncio.CancelledError) else 500
        breaker.abandon(permit)
        raise
    else:
        if isinstance(result, (ChatCompletion, EmbeddingResponse)):
            event.usage = result.usage
            observation.span.set_attribute("gen_ai.response.model", result.model.split("/", 1)[-1])
            event.ttfb_ms = round((clock() - started) * 1000, 2)
            breaker.finish(permit, False)
        else:
            streaming = True
            return DeadlineStream(
                result, deadline, clock, breaker, permit, event, started, observation
            )
        return result
    finally:
        event.duration_ms = round((clock() - started) * 1000, 2)
        unbind(token)
        if not streaming:
            observation.finish()


async def _call(request: ModelRequest, target: Target, remaining: float) -> ModelResult:
    try:
        async with asyncio.timeout(max(0, remaining)):
            if isinstance(request, ChatCompletionRequest):
                if request.stream:
                    return await target.adapter.open_chat_stream(request, target.model)
                return await target.adapter.chat(request, target.model)
            return await target.adapter.embed(request, target.model)
    except TimeoutError:
        raise deadline_error() from None


def _new_event(
    request: ModelRequest, target: Target, execution: Execution, catalog: Catalog
) -> UsageEvent:
    return UsageEvent(
        execution.principal,
        execution.request_id,
        target.price,
        catalog,
        "chat" if isinstance(request, ChatCompletionRequest) else "embeddings",
        isinstance(request, ChatCompletionRequest) and request.stream,
        requested_at=execution.requested_at,
        attempt=len(execution.events) + 1,
        fallback_from=(
            execution.requested_model
            if f"{target.adapter.name}/{target.model}" != execution.requested_model
            else None
        ),
    )
