"""Deliberate non-secret configuration allowlist. Never serialize Settings itself."""

import os
import re
from importlib.metadata import version
from urllib.parse import urlsplit

from llm_gateway.catalog import load_catalog
from llm_gateway.config import Settings
from llm_gateway.guardrails.policy import DEFAULTS
from llm_gateway.providers.defaults import DEFAULT_BASE_URLS


def provider_settings(settings: Settings) -> list[dict[str, object]]:
    return [
        {
            "provider": name,
            "enabled": block.api_key is not None,
            "key_configured": block.api_key is not None,
            "host": urlsplit(str(block.base_url or default)).hostname,
        }
        for name, default in DEFAULT_BASE_URLS.items()
        for block in [getattr(settings.providers, name)]
    ]


def public_settings(settings: Settings) -> dict[str, object]:
    limits = settings.limits
    recovery = settings.resilience
    commit = os.environ.get("GATEWAY_GIT_COMMIT", "")
    return {
        "gateway_version": version("llm-gateway"),
        "git_commit": commit if re.fullmatch(r"[0-9a-f]{7,40}", commit) else None,
        "catalog_version": load_catalog().version,
        "providers": provider_settings(settings),
        "limits": {
            "rpm": limits.default_rpm,
            "tpm": limits.default_tpm,
            "max_concurrency": limits.default_max_concurrency,
            "monthly_budget_usd": format(limits.default_monthly_budget_usd, "f"),
            "alert_threshold": format(limits.default_alert_threshold, "f"),
        },
        "guardrails": dict(DEFAULTS),
        "cache": {"enabled": settings.cache.enabled, "ttl_s": settings.cache.ttl_s},
        "verified_key_cache_ttl_s": settings.key_cache_ttl_s,
        "redis_fail_mode": limits.fail_mode,
        "retry": {
            "max_retries": recovery.max_retries,
            "base_s": recovery.retry_base_s,
            "cap_s": recovery.retry_cap_s,
            "read_timeouts": recovery.retry_read_timeouts,
            "budget_ratio": recovery.retry_budget_ratio,
            "minimum": recovery.retry_budget_min_per_window,
            "window_s": recovery.retry_window_s,
            "deadline_s": recovery.deadline_s,
        },
        "circuit_breaker": {
            "window_s": recovery.breaker_window_s,
            "min_calls": recovery.breaker_min_calls,
            "failure_ratio": recovery.breaker_failure_ratio,
            "open_s": recovery.breaker_open_s,
        },
        "usage_writer": {
            "queue_size": settings.usage_queue_size,
            "batch_size": settings.usage_batch_size,
            "flush_interval_s": settings.usage_flush_interval_s,
            "shutdown_timeout_s": settings.usage_shutdown_timeout_s,
        },
        "metrics_enabled": settings.metrics.enabled,
        "tracing_enabled": settings.tracing.otlp_endpoint is not None,
    }
