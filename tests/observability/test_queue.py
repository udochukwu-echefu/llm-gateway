from collections.abc import Sequence

from prometheus_client import CollectorRegistry

from llm_gateway.observability.metrics import Metrics
from llm_gateway.usage.record import UsageRecord
from llm_gateway.usage.writer import UsageWriter
from tests.usage.test_writer import sample_record


async def test_queue_drop_depth_and_failed_batch_loss_are_counted() -> None:
    async def fail(records: Sequence[UsageRecord]) -> None:
        raise ConnectionError("test outage")

    async def no_sleep(delay: float) -> None:
        pass

    metrics = Metrics(CollectorRegistry())
    writer = UsageWriter(fail, max_size=1, batch_size=1, sleep=no_sleep, metrics=metrics)
    writer.enqueue(sample_record())
    writer.enqueue(sample_record())
    assert metrics.registry.get_sample_value("lgw_usage_queue_depth") == 1
    assert metrics.registry.get_sample_value("lgw_usage_records_dropped_total") == 1

    writer.start()
    await writer.stop()

    assert metrics.registry.get_sample_value("lgw_usage_queue_depth") == 0
    assert metrics.registry.get_sample_value("lgw_usage_records_lost_total") == 1
