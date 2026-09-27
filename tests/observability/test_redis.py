from prometheus_client import CollectorRegistry
from redis.asyncio import Redis

from llm_gateway.limits.service import LimitService
from llm_gateway.observability.metrics import Metrics


async def test_redis_errors_count_every_failure_despite_log_throttling() -> None:
    async def fail() -> None:
        raise ConnectionError("test outage")

    service = LimitService(Redis(), clock=lambda: 1.0)
    service.metrics = Metrics(CollectorRegistry())

    await service.safe(fail)
    await service.safe(fail)

    assert (
        service.metrics.registry.get_sample_value("lgw_redis_errors_total", {"operation": "limits"})
        == 2
    )
