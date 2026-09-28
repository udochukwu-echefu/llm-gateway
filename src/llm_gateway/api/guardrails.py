"""Attach a request-local guard before admission, then wrap billable output."""

from collections.abc import Awaitable, Callable

from fastapi import Request

from llm_gateway.errors import GatewayError
from llm_gateway.guardrails.scheduling import inspect_large
from llm_gateway.guardrails.session import GuardrailSession
from llm_gateway.guardrails.stream import GuardedStream
from llm_gateway.providers.base import ChatStream
from llm_gateway.resilience.execution import Execution
from llm_gateway.schemas.chat import ChatCompletion
from llm_gateway.schemas.embeddings import EmbeddingResponse
from llm_gateway.tenants.auth import Principal


def begin_guardrails(request: Request) -> GuardrailSession:
    principal: Principal = request.state.principal
    session = GuardrailSession(principal.guardrails)
    request.state.guardrails = session
    return session


async def guarded_call(
    session: GuardrailSession,
    call: Callable[[], Awaitable[ChatCompletion | ChatStream | EmbeddingResponse]],
    execution: Execution,
) -> ChatCompletion | ChatStream | EmbeddingResponse:
    result = await call()
    if isinstance(result, ChatCompletion):
        try:
            return await inspect_large(lambda: session.protect_output(result), result)
        except GatewayError as exc:
            execution.events[-1].outcome = "upstream_error"
            execution.events[-1].status_code = exc.status_code
            raise
    if isinstance(result, EmbeddingResponse):
        return result
    return GuardedStream(result, session)
