import pytest
from pydantic import ValidationError

from llm_gateway.errors import GatewayError
from llm_gateway.resilience.configuration import ResilienceSettings
from llm_gateway.resilience.retry import RetryBudget, retry_delay


def test_retry_budget_recovers_after_rolling_window() -> None:
    now = [0.0]
    budget = RetryBudget(ResilienceSettings(), lambda: now[0])
    for _ in range(5):
        budget.first()
    assert budget.take()
    assert not budget.take()
    now[0] = 60
    assert not budget.take()
    for _ in range(5):
        budget.first()
    assert budget.take()


@pytest.mark.parametrize("retry", [0, 1, 2, 10])
@pytest.mark.parametrize("random", [0.0, 0.3, 0.999])
def test_full_jitter_bounds(retry: int, random: float) -> None:
    error = GatewayError(502, "failed", type="upstream_error", code="failed")
    delay = retry_delay(error, retry, ResilienceSettings(), lambda: random)
    assert delay == random * min(2, 0.25 * 2**retry)


@pytest.mark.parametrize(
    ("value", "expected"), [("1", 1), ("2", 2), ("3", None), ("Thu, 01 Jan 1970 00:00:01 GMT", 1)]
)
def test_retry_after_is_honoured_or_exhausted(value: str, expected: float | None) -> None:
    error = GatewayError(
        429, "wait", type="upstream_error", code="failed", headers={"retry-after": value}
    )
    assert retry_delay(error, 0, ResilienceSettings(), lambda: 0.5, lambda: 0) == expected


@pytest.mark.parametrize(
    "values",
    [
        {"max_retries": -1},
        {"deadline_s": 0},
        {"breaker_min_calls": 0},
        {"breaker_failure_ratio": 1.1},
        {"retry_budget_ratio": -1},
        {"retry_base_s": 3},
        {"deadline_s": float("inf")},
    ],
)
def test_invalid_resilience_settings_fail_startup(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ResilienceSettings.model_validate(values)
