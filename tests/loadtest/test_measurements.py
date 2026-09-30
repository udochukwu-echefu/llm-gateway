from typing import Any
from unittest.mock import Mock

import pytest

from loadtest.measurements import container_sample, overhead, snapshot, usage_counts


def test_compose_resource_sampling_does_not_pass_multiple_service_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = Mock(return_value='{"Name":"gateway", "CPUPerc":"1%"}\n')
    monkeypatch.setattr("loadtest.measurements.compose", command)

    result = container_sample()

    assert result["containers"] == [{"Name": "gateway", "CPUPerc": "1%"}]
    assert command.call_args.args == ("stats", "--no-stream", "--format", "{{json .}}")


def test_prometheus_aggregates_buckets_before_computing_replica_percentiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expressions: list[str] = []

    def query(expression: str) -> list[dict[str, Any]]:
        expressions.append(expression)
        return [
            {"metric": {"le": "0.01"}, "value": [0, "99"]},
            {"metric": {"le": "+Inf"}, "value": [0, "100"]},
        ]

    monkeypatch.setattr("loadtest.measurements.query", query)

    values = snapshot(2, "/v1/chat/completions")
    quantiles = overhead({}, values)

    assert expressions[0].startswith("sum by (le)")
    assert 'instance=~"gateway-loadtest-1:9464|gateway-loadtest-2:9464"' in expressions[0]
    assert quantiles["p99"] == pytest.approx(10)


def test_accounting_query_rejects_non_generated_org_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = Mock()
    monkeypatch.setattr("loadtest.measurements.compose", command)

    with pytest.raises(ValueError, match="generated benchmark"):
        usage_counts("loadtest-'; DROP TABLE organizations;")

    command.assert_not_called()
