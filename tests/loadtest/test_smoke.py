from typing import Any
from unittest.mock import Mock

import pytest

from loadtest.smoke import main


@pytest.mark.parametrize(
    ("p99", "errors", "dropped"),
    [(None, 0, 0), (50, 0, 0), (1, 0.001, 0), (1, 0, 1)],
)
def test_ci_smoke_fails_closed_for_missing_metrics_errors_and_overload(
    monkeypatch: pytest.MonkeyPatch,
    p99: float | None,
    errors: float,
    dropped: int,
) -> None:
    monkeypatch.setattr("loadtest.smoke.setup", Mock())
    result: dict[str, Any] = {
        "overhead_ms": {"p99": p99},
        "error_rate": errors,
        "dropped_iterations": dropped,
        "measurement_complete": True,
    }
    monkeypatch.setattr("loadtest.smoke.run_once", Mock(return_value=result))

    with pytest.raises(SystemExit, match="Smoke failed"):
        main()


def test_ci_smoke_is_one_thirty_second_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("loadtest.smoke.setup", Mock())
    run = Mock(
        return_value={
            "overhead_ms": {"p99": 49},
            "error_rate": 0,
            "dropped_iterations": 0,
            "measurement_complete": True,
        }
    )
    monkeypatch.setattr("loadtest.smoke.run_once", run)

    main()

    run.assert_called_once_with("smoke", 5, 30, 1, 1)
