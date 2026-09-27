"""Off-path, conservative Redis budget correction from durable and queued receipts."""

import asyncio
import math
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import structlog

from llm_gateway.errors import GatewayError
from llm_gateway.limits.service import LimitService, month_end, picos
from llm_gateway.usage.repository import PostgresUsageRepository
from llm_gateway.usage.writer import UsageWriter

log = structlog.get_logger("llm_gateway.budget_reconciliation")


class BudgetReconciler:
    def __init__(
        self,
        service: LimitService,
        usage: PostgresUsageRepository,
        writer: UsageWriter,
        *,
        interval: float = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.service = service
        self.usage = usage
        self.writer = writer
        self.interval = interval
        self.clock = clock
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def run_once(self) -> None:
        now = datetime.fromtimestamp(self.clock(), UTC)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = month_end(now)
        try:
            teams = await self.usage.active_teams(start, end)
            teams.update(self.writer.pending_team_ids(start, end))
        except Exception as exc:
            log.error("budget_reconciliation_query_failed", error_type=type(exc).__name__)
            return
        for team in teams:
            try:
                await self.service.safe(lambda team=team: self._correct(team, start, end, now))
            except GatewayError:
                # Fail-closed affects admissions, not the background worker's lifetime.
                continue

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.run_once()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self.interval)

    async def _correct(
        self,
        team: uuid.UUID,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> None:
        key = f"lgw:budget:{team}:{now:%Y-%m}"
        lock = f"{key}:lock"
        owner = uuid.uuid4().hex
        if not cast(bool, await self.service.client.set(lock, owner, nx=True, ex=5)):
            return
        try:
            async with asyncio.timeout(4):

                async def persisted() -> dict[uuid.UUID, Decimal]:
                    return {team: await self.usage.month_spend(team, start, end)}

                totals = await self.writer.spend_snapshot(start, end, persisted, team)
                ttl = max(1, math.ceil((month_end(now) - now).total_seconds()) + 60)
                await self.service.scripts.call("reconcile", [key], [picos(totals[team]), ttl])
        finally:
            await self.service.scripts.call("unlock", [lock], [owner])
