"""Best-effort, bounded accounting: never await storage in a user request."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from time import monotonic

import structlog

from llm_gateway.usage.record import UsageRecord

log = structlog.get_logger("llm_gateway.usage")
Sink = Callable[[Sequence[UsageRecord]], Awaitable[None]]


class UsageWriter:
    def __init__(
        self,
        sink: Sink,
        *,
        max_size: int = 10_000,
        batch_size: int = 500,
        interval: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.queue: asyncio.Queue[UsageRecord] = asyncio.Queue(maxsize=max_size)
        self.sink = sink
        self.batch_size = batch_size
        self.interval = interval
        self.sleep = sleep
        self.clock = clock
        self.accepting = True
        self.dropped = 0
        self._drops_since_log = 0
        self._last_drop_log: float | None = None
        self.lost = 0
        self.flushed = 0
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._working = False
        self._inflight = 0
        self._pending: dict[uuid.UUID, UsageRecord] = {}
        self._settlement_lock = asyncio.Lock()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def enqueue(self, record: UsageRecord) -> None:
        try:
            if not self.accepting:
                raise asyncio.QueueFull
            self.queue.put_nowait(record)
            if record.cost_status == "priced" and record.cost_usd is not None:
                self._pending[record.id] = record
        except asyncio.QueueFull:
            self.dropped += 1
            self._drops_since_log += 1
            now = self.clock()
            if self._last_drop_log is None or now - self._last_drop_log >= 1:
                log.error("usage_dropped", drops=self._drops_since_log, total_drops=self.dropped)
                self._last_drop_log = now
                self._drops_since_log = 0

    async def stop(self, drain_seconds: float = 10.0) -> None:
        self.accepting = False
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, drain_seconds)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                self._task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._task
        remaining = self.queue.qsize()
        self.lost += remaining + self._inflight
        log.info("usage_writer_stopped", flushed=self.flushed, lost=self.lost + self.dropped)

    async def spend_snapshot(
        self,
        start: datetime,
        end: datetime,
        persisted: Callable[[], Awaitable[dict[uuid.UUID, Decimal]]],
        team: uuid.UUID | None = None,
    ) -> dict[uuid.UUID, Decimal]:
        """Observe Postgres and uncommitted local receipts without a flush in between."""
        async with self._settlement_lock:
            totals = await persisted()
            for record in self._pending.values():
                if team is not None and record.team_id != team:
                    continue
                if start <= record.created_at < end and record.cost_usd is not None:
                    totals[record.team_id] = (
                        totals.get(record.team_id, Decimal(0)) + record.cost_usd
                    )
            return totals

    def pending_team_ids(self, start: datetime, end: datetime) -> set[uuid.UUID]:
        return {
            record.team_id for record in self._pending.values() if start <= record.created_at < end
        }

    async def _run(self) -> None:
        while self.accepting or not self.queue.empty():
            try:
                first = await self._next(self.interval)
            except TimeoutError:
                continue
            if first is None:
                continue
            batch = [first]
            self._working = True
            deadline = self.clock() + self.interval
            while len(batch) < self.batch_size:
                remaining = deadline - self.clock()
                if remaining <= 0 or (not self.accepting and self.queue.empty()):
                    break
                try:
                    next_record = await self._next(remaining)
                    if next_record is None:
                        break
                    batch.append(next_record)
                except TimeoutError:
                    break
            self._inflight = len(batch)
            try:
                async with self._settlement_lock:
                    flushed = await self._flush(batch)
                    if flushed:
                        for record in batch:
                            self._pending.pop(record.id, None)
            except asyncio.CancelledError:
                self.lost += len(batch)
                raise
            finally:
                self._inflight = 0
                self._working = False

    async def _next(self, wait_seconds: float) -> UsageRecord | None:
        if not self.accepting:
            return self.queue.get_nowait() if not self.queue.empty() else None
        getter = asyncio.create_task(self.queue.get())
        stopper = asyncio.create_task(self._stop.wait())
        try:
            done, _ = await asyncio.wait(
                {getter, stopper}, timeout=wait_seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                return getter.result()
            if stopper in done:
                return None
            raise TimeoutError
        finally:
            for task in (getter, stopper):
                if not task.done():
                    task.cancel()
            await asyncio.gather(getter, stopper, return_exceptions=True)

    async def _flush(self, batch: list[UsageRecord]) -> bool:
        for attempt in range(3):
            try:
                await self.sink(batch)
                self.flushed += len(batch)
                return True
            except Exception:
                log.exception("usage_insert_failed", count=len(batch), attempt=attempt + 1)
                if attempt < 2:
                    await self.sleep(0.1 * (2**attempt))
        self.lost += len(batch)
        log.error("usage_batch_lost", count=len(batch))
        for record in batch:
            self._pending.pop(record.id, None)
        return False
