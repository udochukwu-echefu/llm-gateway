"""Zero and NULL have deliberately different meanings for team overrides."""

from decimal import Decimal

import pytest
from starlette.requests import Request

from llm_gateway.config import LimitsSettings, Settings
from llm_gateway.limits.configuration import LimitOverrides, resolve
from llm_gateway.tenants.auth import client_ip


def test_null_inherits_defaults_but_explicit_zero_disables_limit() -> None:
    defaults = LimitsSettings(
        default_rpm=20,
        default_tpm=100,
        default_max_concurrency=3,
        default_monthly_budget_usd=Decimal("5"),
    )

    inherited = resolve(LimitOverrides(), defaults)
    disabled = resolve(
        LimitOverrides(rpm=0, tpm=0, max_concurrency=0, monthly_budget_usd=Decimal(0)), defaults
    )

    assert inherited.rpm == 20
    assert inherited.tpm == 100
    assert inherited.max_concurrency == 3
    assert inherited.monthly_budget_usd == Decimal("5")
    assert disabled.rpm == disabled.tpm == disabled.max_concurrency == 0
    assert disabled.monthly_budget_usd == 0


def test_invalid_limit_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        LimitsSettings(default_rpm=-1)
    with pytest.raises(ValueError, match=r"open.*closed"):
        LimitsSettings(fail_mode="unknown")  # pyright: ignore[reportArgumentType]  # intentionally invalid configuration


def test_lease_ttl_must_outlast_provider_stall() -> None:
    with pytest.raises(ValueError, match="Lease TTL must exceed"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]  # no developer env file
            providers={"groq": {"api_key": "fake-test-key"}},
            limits={"lease_ttl_s": 60},
        )


def test_x_forwarded_for_is_ignored_without_trusted_proxy_hops() -> None:
    request = Request(
        {
            "type": "http",
            "client": ("192.0.2.2", 1234),
            "headers": [(b"x-forwarded-for", b"203.0.113.3, 198.51.100.4")],
        }
    )

    assert client_ip(request, 0) == "192.0.2.2"
    assert client_ip(request, 1) == "198.51.100.4"
    assert client_ip(request, 2) == "203.0.113.3"
    assert client_ip(request, 3) == "192.0.2.2"


def test_rpm_burst_must_be_positive_or_unset() -> None:
    assert LimitsSettings().rpm_burst is None
    assert LimitsSettings(rpm_burst=30).rpm_burst == 30
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        LimitsSettings(rpm_burst=0)
