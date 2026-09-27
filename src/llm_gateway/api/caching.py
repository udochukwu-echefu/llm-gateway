"""Place response caching between request-rate admission and billable work."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal
from typing import Literal, cast

from fastapi import Request

from llm_gateway.cache.key import cache_key
from llm_gateway.errors import GatewayError
from llm_gateway.gateway_state import get_state
from llm_gateway.observability.tracing import current, span
from llm_gateway.providers.base import ChatStream
from llm_gateway.resilience.execution import Execution
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse
from llm_gateway.tenants.admission import admit_after_cache, admit_rpm
from llm_gateway.usage.record import UsageEvent

Result = ChatCompletion | EmbeddingResponse | ChatStream


async def execute_with_cache[R: (ChatCompletion, EmbeddingResponse)](
    http: Request,
    request: ChatCompletionRequest | EmbeddingRequest,
    execution: Execution,
    endpoint: Literal["chat", "embeddings"],
    response_type: type[R],
    call: Callable[[], Awaitable[Result]],
) -> tuple[Result, str]:
    state = get_state(http)
    try:
        await admit_rpm(http)
        mode = http.headers.get("x-lgw-cache", "").lower()
        cache = state.response_cache
        if mode == "disabled" or cache is None or (endpoint == "chat" and mode != "enabled"):
            return await _uncached(http, call), "disabled"
        if isinstance(request, ChatCompletionRequest) and (request.stream or (request.n or 1) > 1):
            return await _uncached(http, call), "bypass"
        key = cache_key(
            execution.principal.team_id,
            endpoint,
            execution.requested_model,
            request,
            state.catalog.version,
        )
        with span("cache.lookup") as lookup_span:
            data, available = await cache.lookup(key)
            lookup_span.set_attribute(
                "result", "hit" if data is not None else "miss" if available else "bypass"
            )
        if not available:
            return await _uncached(http, call), "bypass"
        if data is not None:
            result = _decode(data, response_type)
            if result is not None:
                _hit(http, execution, endpoint, result)
                return result, "hit"
        flight, leader = cache.enter(key)
        if not leader:
            try:
                data = await asyncio.wait_for(
                    asyncio.shield(flight), state.settings.resilience.deadline_s
                )
            except TimeoutError:
                data = None
            if data is not None:
                result = _decode(data, response_type)
                if result is not None:
                    _hit(http, execution, endpoint, result)
                    return result, "hit"
            return await _uncached(http, call), "miss"
        data = None
        try:
            result = await _uncached(http, call)
            if _complete(result, execution) and isinstance(result, response_type):
                candidate = result.model_dump_json(exclude_unset=True).encode()
                if len(candidate) <= cache.max_bytes:
                    data = candidate
                    await cache.store(key, data)
            return result, "miss"
        finally:
            cache.leave(key, flight, data)
    except GatewayError as exc:
        exc.headers.update(execution.headers)
        exc.headers.setdefault("x-lgw-cache", "bypass")
        raise


async def _uncached(http: Request, call: Callable[[], Awaitable[Result]]) -> Result:
    await admit_after_cache(http)
    return await call()


def _decode[R: (ChatCompletion, EmbeddingResponse)](
    data: bytes, response_type: type[R]
) -> R | None:
    try:
        return response_type.model_validate_json(data)
    except ValueError:
        return None


def _complete(result: Result, execution: Execution) -> bool:
    if not execution.events or execution.events[-1].fallback_from is not None:
        return False
    if isinstance(result, ChatCompletion):
        return bool(result.choices) and all(
            choice.finish_reason is not None for choice in result.choices
        )
    return isinstance(result, EmbeddingResponse) and bool(result.data)


def _hit(
    http: Request,
    execution: Execution,
    endpoint: Literal["chat", "embeddings"],
    result: ChatCompletion | EmbeddingResponse,
) -> None:
    state = get_state(http)
    provider, model = execution.requested_model.split("/", 1)
    price = state.catalog.find(
        cast(ProviderName, provider), model, "chat" if endpoint == "chat" else "embedding"
    )
    if price is None:
        raise RuntimeError("Resolved model has no catalogue price")
    event = UsageEvent(
        execution.principal,
        execution.request_id,
        price,
        state.catalog,
        endpoint,
        False,
        requested_at=execution.requested_at,
        alias=execution.alias,
    )
    event.usage = result.usage
    receipt = event.finish(None, None)
    http.state.cache_record = replace(
        receipt,
        outcome="cache_hit",
        cost_status="cached",
        cost_usd=Decimal(0),
        saved_usd=receipt.cost_usd,
    )
    telemetry = current.get()
    if telemetry is not None and receipt.cost_usd is not None:
        telemetry.metrics.cache_saved.labels(endpoint).inc(float(receipt.cost_usd))
