"""Best-effort, bounded accounting: never await storage in a user request."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
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
        self.lost = 0
        self.flushed = 0
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._working = False
        self._inflight = 0

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def enqueue(self, record: UsageRecord) -> None:
        try:
            if not self.accepting:
                raise asyncio.QueueFull
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            self.dropped += 1
            log.error("usage_dropped", request_id=record.request_id, drops=self.dropped)

    async def stop(self, drain_seconds: float = 10.0) -> None:
        self.accepting = False
        self._stop.set()
        if self._task is not None:
            try:
                if self.queue.empty() and not self._working:
                    self._task.cancel()
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
                await self._flush(batch)
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

    async def _flush(self, batch: list[UsageRecord]) -> None:
        for attempt in range(3):
            try:
                await self.sink(batch)
                self.flushed += len(batch)
                return
            except Exception:
                log.exception("usage_insert_failed", count=len(batch), attempt=attempt + 1)
                if attempt < 2:
                    await self.sleep(0.1 * (2**attempt))
        self.lost += len(batch)
        log.error("usage_batch_lost", count=len(batch))
