"""CLI displays resolved values, not Python model representations or pico-dollar units."""

from decimal import Decimal

from llm_gateway.admin.service.limits import LiveLimits, render_limits
from llm_gateway.config import LimitsSettings
from llm_gateway.limits.configuration import LimitOverrides
from llm_gateway.limits.service import picos


def test_aligned_table_includes_sources_usd_percent_and_live_usage() -> None:
    defaults = LimitsSettings(
        default_rpm=20,
        default_tpm=100,
        default_max_concurrency=2,
        default_monthly_budget_usd=Decimal("2"),
    )
    overrides = LimitOverrides(rpm=5, tpm=0, monthly_budget_usd=Decimal("1.25"))
    live = LiveLimits(picos(Decimal("0.625")), 4, -1, 1)

    output = render_limits("example", "team", overrides, defaults, live)
    lines = output.splitlines()

    assert lines[2].split() == ["RPM", "5", "override"]
    assert lines[3].split() == ["TPM", "unlimited", "unlimited"]
    assert lines[4].split() == ["Max", "concurrency", "2", "default"]
    assert lines[5].split() == ["Monthly", "budget", "$1.25", "override"]
    assert "$0.625000000000 (50.00%)" in lines[7]
    assert "Requests remaining" in lines[8]
    assert "4" in lines[8]
    assert "Tokens remaining" in lines[9]
    assert "unlimited" in lines[9]
    assert "Active leases" in lines[10]
    assert "1" in lines[10]
    assert "cache TTL" in lines[-1]
    assert "Decimal(" not in output


def test_unavailable_usage_does_not_guess_spend_or_remaining() -> None:
    output = render_limits("example", "team", LimitOverrides(), LimitsSettings(), None)

    assert "Monthly budget" in output
    assert "unlimited" in output
    assert output.count("unavailable") == 4
