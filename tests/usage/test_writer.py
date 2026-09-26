import asyncio
import uuid
from collections.abc import Callable, Sequence

from llm_gateway.catalog import load_catalog
from llm_gateway.schemas.chat import Usage
from llm_gateway.tenants.auth import Principal
from llm_gateway.usage.record import UsageEvent, UsageRecord
from llm_gateway.usage.writer import UsageWriter


def sample_record() -> UsageRecord:
    catalog = load_catalog()
    event = UsageEvent(
        Principal(uuid.uuid4(), uuid.uuid4(), "test-key"),
        "request-1",
        catalog.models[0],
        catalog,
        "chat",
        False,
    )
    return event.finish(1, 1)


def test_disconnect_after_usage_was_received_still_has_priced_cost() -> None:
    catalog = load_catalog()
    event = UsageEvent(
        Principal(uuid.uuid4(), uuid.uuid4(), "test-key"),
        "request-1",
        catalog.models[0],
        catalog,
        "chat",
        True,
    )
    event.outcome = "client_disconnected"
    event.usage = Usage(prompt_tokens=10, completion_tokens=2, total_tokens=12)

    record = event.finish(2, 1)

    assert record.cost_status == "priced"
    assert record.cost_usd is not None


async def test_batch_flushes_at_size_without_waiting_for_interval() -> None:
    batches: list[int] = []

    async def sink(records: Sequence[UsageRecord]) -> None:
        batches.append(len(records))

    writer = UsageWriter(sink, batch_size=2, interval=60)
    writer.start()
    writer.enqueue(sample_record())
    writer.enqueue(sample_record())
    await asyncio.wait_for(_until(lambda: bool(batches)), 1)
    await writer.stop()

    assert batches == [2]


async def test_batch_flushes_at_time_when_not_full() -> None:
    batches: list[int] = []

    async def sink(records: Sequence[UsageRecord]) -> None:
        batches.append(len(records))

    writer = UsageWriter(sink, batch_size=10, interval=0.01)
    writer.start()
    writer.enqueue(sample_record())
    await asyncio.wait_for(_until(lambda: bool(batches)), 1)
    await writer.stop()

    assert batches == [1]


async def test_queue_full_drops_immediately_and_counts_loss() -> None:
    async def sink(records: Sequence[UsageRecord]) -> None:
        pass

    writer = UsageWriter(sink, max_size=1)
    writer.enqueue(sample_record())

    writer.enqueue(sample_record())

    assert writer.dropped == 1
    assert writer.queue.qsize() == 1


async def test_database_retries_then_succeeds_without_losing_records() -> None:
    calls = 0
    delays: list[float] = []

    async def sink(records: Sequence[UsageRecord]) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("fake unavailable")

    async def sleep(delay: float) -> None:
        delays.append(delay)

    writer = UsageWriter(sink, batch_size=1, sleep=sleep)
    writer.start()
    writer.enqueue(sample_record())
    await asyncio.wait_for(_until(lambda: writer.flushed == 1), 1)
    await writer.stop()

    assert calls == 3
    assert writer.lost == 0
    assert delays == [0.1, 0.2]


async def test_database_give_up_counts_lost_records() -> None:
    calls = 0

    async def sink(records: Sequence[UsageRecord]) -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("fake unavailable")

    async def sleep(delay: float) -> None:
        pass

    writer = UsageWriter(sink, batch_size=1, sleep=sleep)
    writer.start()
    writer.enqueue(sample_record())
    await asyncio.wait_for(_until(lambda: writer.lost == 1), 1)
    await writer.stop()

    assert calls == 3
    assert writer.flushed == 0


async def test_shutdown_drains_pending_and_rejects_late_events() -> None:
    received: list[UsageRecord] = []

    async def sink(records: Sequence[UsageRecord]) -> None:
        received.extend(records)

    writer = UsageWriter(sink, batch_size=10, interval=60)
    writer.start()
    writer.enqueue(sample_record())
    await writer.stop()
    writer.enqueue(sample_record())

    assert len(received) == 1
    assert writer.dropped == 1


async def test_shutdown_timeout_counts_inflight_record_as_lost() -> None:
    entered = asyncio.Event()

    async def sink(records: Sequence[UsageRecord]) -> None:
        entered.set()
        await asyncio.Event().wait()

    writer = UsageWriter(sink, batch_size=1)
    writer.start()
    writer.enqueue(sample_record())
    await entered.wait()

    await writer.stop(0.01)

    assert writer.lost == 1
    assert writer.flushed == 0


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(100_000):
        if condition():
            return
        await asyncio.sleep(0)
