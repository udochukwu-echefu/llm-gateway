"""Settle all attempts before enqueuing receipts, preserving budget reconciliation order."""

import time
from dataclasses import replace

import anyio
import structlog
from starlette.types import Scope

from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.session import GuardrailSession
from llm_gateway.observability.tracing import current, span
from llm_gateway.usage.record import UsageEvent, UsageRecord

log = structlog.get_logger("llm_gateway.usage")


async def finalize_usage(
    scope: Scope, started: float, first_byte_at: float | None, status: int | None
) -> None:
    state = scope.get("state", {})
    events = state.get("usage_events", [state.get("usage_event")])
    records: list[UsageRecord] = []
    for event in events:
        if not isinstance(event, UsageEvent) or not event.sent:
            continue
        try:
            if event.outcome == "success":
                event.status_code = status or 500
            records.append(
                event.finish(
                    round((time.perf_counter() - started) * 1000, 2),
                    None if first_byte_at is None else round((first_byte_at - started) * 1000, 2),
                )
            )
        except Exception:
            log.exception("usage_enqueue_failed", request_id=event.request_id)
    cache_record = state.get("cache_record")
    if isinstance(cache_record, UsageRecord):
        records.append(cache_record)
    guardrails = state.get("guardrails")
    if isinstance(guardrails, GuardrailSession):
        records = [
            replace(record, redaction_count=guardrails.redaction_count) for record in records
        ]
    admitted = state.get("limit_admission")
    if admitted is not None:
        team, lease, limits = admitted
        service = get_app_state(scope["app"]).limits
        if service is not None:
            try:
                with anyio.CancelScope(shield=True):
                    await service.finish_records(team, lease, records, limits)
            except Exception:
                log.exception("limits_finalize_failed")
    for record in records:
        try:
            with span("usage.enqueue"):
                telemetry = current.get()
                if telemetry is not None:
                    telemetry.metrics.record_usage(record)
                get_app_state(scope["app"]).usage_writer.enqueue(record)
        except Exception:
            log.exception("usage_enqueue_failed", request_id=record.request_id)
