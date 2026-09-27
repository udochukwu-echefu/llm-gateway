import pytest
from pydantic import ValidationError

from llm_gateway.observability.configuration import MetricsSettings, TracingSettings
from llm_gateway.observability.tracing import make_provider


def test_default_metrics_socket_is_private_and_tracing_export_disabled() -> None:
    settings = MetricsSettings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 9464
    assert make_provider(TracingSettings()) is None
    assert TracingSettings().sample_ratio == 1.0
    assert TracingSettings().propagate_to_providers is False


@pytest.mark.parametrize("values", [{"host": ""}, {"port": 0}, {"port": 65536}])
def test_invalid_metrics_configuration_fails(values: dict[str, str | int]) -> None:
    with pytest.raises(ValidationError):
        MetricsSettings.model_validate(values)


@pytest.mark.parametrize(
    "values",
    [
        {"sample_ratio": -0.1},
        {"sample_ratio": 1.1},
        {"sample_ratio": float("nan")},
        {"otlp_endpoint": "ftp://collector"},
        {"otlp_endpoint": "https://user:password@collector/v1/traces"},
    ],
)
def test_invalid_tracing_configuration_fails(values: dict[str, str | float]) -> None:
    with pytest.raises(ValidationError):
        TracingSettings.model_validate(values)
