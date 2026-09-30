"""Resolve documented Kimi JSON jobs without resubmitting accepted inference.

The resilience layer's single asyncio deadline includes submission, every poll and
body reads. Cancellation stops local polling; NVIDIA documents no remote cancel API.
"""

import asyncio
from typing import Any
from uuid import UUID

import httpx

from llm_gateway.errors import GatewayError
from llm_gateway.providers.transport import UpstreamClient

POLL_INTERVAL_S = 0.25


async def resolve_pending(
    transport: UpstreamClient, response: httpx.Response, payload: dict[str, Any]
) -> httpx.Response:
    if response.status_code != 202:
        return response
    await response.aclose()
    if payload["model"] != "moonshotai/kimi-k3" or payload.get("stream"):
        raise GatewayError(
            502,
            "The model provider returned an unsupported queued response.",
            type="upstream_error",
            code="upstream_pending_unsupported",
            upstream_status=202,
        )
    request_id = _request_id(response)
    try:
        while True:
            # Pace immediate pending responses; the outer deadline never resets per poll.
            await asyncio.sleep(POLL_INTERVAL_S)
            response = await transport.get(f"status/{request_id}")
            if response.status_code == 200:
                response.extensions["gateway_retry_allowed"] = False
                return response
            await response.aclose()
            if response.status_code != 202:
                raise _invalid_pending()
    except GatewayError as exc:
        # The POST was accepted: retrying inference could create a second charged job.
        exc.retry_allowed = False
        raise


def _request_id(response: httpx.Response) -> str:
    value = response.headers.get("nvcf-reqid", "")
    try:
        return str(UUID(value))
    except ValueError:
        raise _invalid_pending() from None


def _invalid_pending() -> GatewayError:
    return GatewayError(
        502,
        "The model provider returned an invalid queued response.",
        type="upstream_error",
        code="upstream_invalid_response",
        retry_allowed=False,
    )
