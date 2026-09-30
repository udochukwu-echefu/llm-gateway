import pytest

from loadtest.reporting import memory_bytes, queue_maximum, resource_summary


def test_docker_memory_units_are_not_conflated() -> None:
    assert memory_bytes(" 1MiB ") == 1024**2
    assert memory_bytes("1MB") == 1000**2
    with pytest.raises(ValueError, match="Unknown Docker memory unit"):
        memory_bytes("missing")


def test_missing_cpu_and_queue_samples_are_not_zero() -> None:
    run = {"container_samples": [{"error": "unavailable"}], "queue": []}

    assert resource_summary(run) == {}
    assert queue_maximum(run) is None
