from pathlib import Path
from unittest.mock import Mock

import pytest

from loadtest.setup import setup


def _private_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = tmp_path / "runtime.env"
    runtime.write_text("synthetic-test-only")
    runtime.chmod(0o600)
    monkeypatch.setattr("loadtest.setup.STATE", tmp_path)
    monkeypatch.setattr("loadtest.setup.prepare_directories", Mock())


def test_setup_waits_for_database_health_before_querying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _private_runtime(tmp_path, monkeypatch)
    compose = Mock(return_value="1")
    monkeypatch.setattr("loadtest.setup.compose", compose)
    monkeypatch.setattr("loadtest.setup._wait_for_readiness", Mock())

    setup()

    assert compose.call_args_list[0].args == ("up", "-d", "--wait", "postgres", "redis")
    assert compose.call_args_list[1].args[:3] == ("exec", "-T", "postgres")


def test_setup_stops_before_database_query_if_health_wait_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _private_runtime(tmp_path, monkeypatch)
    compose = Mock(side_effect=RuntimeError("service health failed"))
    monkeypatch.setattr("loadtest.setup.compose", compose)

    with pytest.raises(RuntimeError, match="service health failed"):
        setup()

    compose.assert_called_once_with("up", "-d", "--wait", "postgres", "redis")
