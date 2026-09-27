from typing import cast

from prometheus_client import CollectorRegistry

from llm_gateway.observability.metrics import Metrics

EXPECTED = {
    "guardrail_findings": ("counter", ("direction", "detector", "action")),
    "requests": ("counter", ("route", "status_class")),
    "request_duration_seconds": ("histogram", ("route",)),
    "time_to_first_byte_seconds": ("histogram", ("route",)),
    "gateway_overhead_seconds": ("histogram", ("route",)),
    "upstream_requests": ("counter", ("provider", "model", "outcome", "alias")),
    "upstream_duration_seconds": ("histogram", ("provider",)),
    "tokens": ("counter", ("provider", "model", "kind")),
    "cost_usd": ("counter", ("provider", "model")),
    "retries": ("counter", ("provider", "reason")),
    "fallbacks": ("counter", ("from_provider", "to_provider")),
    "circuit_state": ("gauge", ("provider",)),
    "rate_limited": ("counter", ("kind",)),
    "auth_failures": ("counter", ("reason",)),
    "usage_queue_depth": ("gauge", ()),
    "usage_records_dropped": ("counter", ()),
    "usage_records_lost": ("counter", ()),
    "redis_errors": ("counter", ("operation",)),
    "inflight_requests": ("gauge", ("route",)),
    "cache_requests": ("counter", ("endpoint", "result")),
    "cache_saved_usd": ("counter", ("endpoint",)),
}


def test_every_registered_metric_has_exact_type_and_bounded_label_names() -> None:
    registry = CollectorRegistry()
    Metrics(registry)
    actual: dict[str, tuple[str, tuple[str, ...]]] = {}

    for collector in registry._collector_to_names:  # pyright: ignore[reportPrivateUsage]  # inspect all registered collectors, including ones with no samples
        labels = cast(tuple[str, ...], vars(collector)["_labelnames"])
        assert set(labels) <= {
            "route",
            "status_class",
            "provider",
            "model",
            "outcome",
            "alias",
            "kind",
            "reason",
            "from_provider",
            "to_provider",
            "operation",
            "endpoint",
            "result",
            "direction",
            "detector",
            "action",
        }
        for metric in collector.collect():
            actual[metric.name.removeprefix("lgw_")] = metric.type, labels

    assert actual == EXPECTED


def test_registries_are_isolated() -> None:
    first, second = CollectorRegistry(), CollectorRegistry()
    Metrics(first).requests.labels("other", "4xx").inc()
    Metrics(second)

    assert (
        first.get_sample_value("lgw_requests_total", {"route": "other", "status_class": "4xx"}) == 1
    )
    assert (
        second.get_sample_value("lgw_requests_total", {"route": "other", "status_class": "4xx"})
        is None
    )
