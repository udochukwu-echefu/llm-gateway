"""Bounded Prometheus instruments; one registry per gateway instance."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from llm_gateway.usage.record import UsageRecord

# Fine resolution around the gateway's 10 ms overhead target, plus provider-scale buckets.
BUCKETS = (
    0.0005,
    0.001,
    0.002,
    0.003,
    0.004,
    0.005,
    0.0075,
    0.01,
    0.0125,
    0.015,
    0.02,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    30,
    60,
)


class Metrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self.guardrail_findings = Counter(
            "lgw_guardrail_findings_total",
            "Detected patterns, never values",
            ("direction", "detector", "action"),
            registry=registry,
        )
        self.requests = Counter(
            "lgw_requests_total", "Client requests", ("route", "status_class"), registry=registry
        )
        self.duration = Histogram(
            "lgw_request_duration_seconds",
            "Full response duration",
            ("route",),
            registry=registry,
            buckets=BUCKETS,
        )
        self.ttfb = Histogram(
            "lgw_time_to_first_byte_seconds",
            "Stream first body byte",
            ("route",),
            registry=registry,
            buckets=BUCKETS,
        )
        self.overhead = Histogram(
            "lgw_gateway_overhead_seconds",
            "Elapsed time excluding provider waits; to first byte for streams",
            ("route",),
            registry=registry,
            buckets=BUCKETS,
        )
        self.upstream_requests = Counter(
            "lgw_upstream_requests_total",
            "Provider attempts",
            ("provider", "model", "outcome", "alias"),
            registry=registry,
        )
        self.upstream_duration = Histogram(
            "lgw_upstream_duration_seconds",
            "Provider attempt duration",
            ("provider",),
            registry=registry,
            buckets=BUCKETS,
        )
        self.tokens = Counter(
            "lgw_tokens_total",
            "Known tokens; cached and reasoning are subsets",
            ("provider", "model", "kind"),
            registry=registry,
        )
        self.cost = Counter(
            "lgw_cost_usd_total",
            "Monitoring trend only; Postgres is the accounting record",
            ("provider", "model"),
            registry=registry,
        )
        self.retries = Counter(
            "lgw_retries_total", "Started retries", ("provider", "reason"), registry=registry
        )
        self.fallbacks = Counter(
            "lgw_fallbacks_total",
            "Started fallback targets",
            ("from_provider", "to_provider"),
            registry=registry,
        )
        self.circuit = Gauge(
            "lgw_circuit_state", "0 closed, 1 half-open, 2 open", ("provider",), registry=registry
        )
        self.rate_limited = Counter(
            "lgw_rate_limited_total", "Admission rejections", ("kind",), registry=registry
        )
        self.auth_failures = Counter(
            "lgw_auth_failures_total", "Failed authentication", ("reason",), registry=registry
        )
        self.queue_depth = Gauge(
            "lgw_usage_queue_depth", "Receipts waiting in the queue", registry=registry
        )
        self.dropped = Counter(
            "lgw_usage_records_dropped_total", "Receipts rejected by the queue", registry=registry
        )
        self.lost = Counter(
            "lgw_usage_records_lost_total",
            "Accepted receipts lost by the writer",
            registry=registry,
        )
        self.redis_errors = Counter(
            "lgw_redis_errors_total", "Redis dependency failures", ("operation",), registry=registry
        )
        self.inflight = Gauge(
            "lgw_inflight_requests", "Active client requests", ("route",), registry=registry
        )
        self.cache_requests = Counter(
            "lgw_cache_requests_total",
            "Response cache decisions",
            ("endpoint", "result"),
            registry=registry,
        )
        self.cache_saved = Counter(
            "lgw_cache_saved_usd_total",
            "Estimated USD avoided on cache hits",
            ("endpoint",),
            registry=registry,
        )

    def record_usage(self, record: UsageRecord) -> None:
        for kind, count in (
            ("prompt", record.prompt_tokens),
            ("completion", record.completion_tokens),
            ("cached", record.cached_tokens),
            ("reasoning", record.reasoning_tokens),
        ):
            if count is not None:
                self.tokens.labels(record.provider, record.model, kind).inc(count)
        if record.cost_usd is not None:
            self.cost.labels(record.provider, record.model).inc(float(record.cost_usd))
