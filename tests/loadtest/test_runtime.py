import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from loadtest.runtime import compose, private_write


def test_compose_excludes_owner_configuration_and_uses_no_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDERS__GROQ__API_KEY", "must-not-copy")
    monkeypatch.setenv("COMPOSE_FILE", "unexpected.yaml")
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout="ok", stderr=""))
    monkeypatch.setattr("loadtest.runtime.subprocess.run", runner)
    monkeypatch.setattr("loadtest.runtime.shutil.which", Mock(return_value="/usr/bin/docker"))

    assert compose("up", "-d") == "ok"

    arguments: list[str] = runner.call_args.args[0]
    environment: dict[str, Any] = runner.call_args.kwargs["env"]
    assert arguments[arguments.index("--env-file") + 1] == "/dev/null"
    assert "GATEWAY_PROVIDERS__GROQ__API_KEY" not in environment
    assert "COMPOSE_FILE" not in environment


def test_failed_cli_does_not_disclose_output(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock(
        return_value=subprocess.CompletedProcess(
            [], 1, stdout="secret sentinel", stderr="secret sentinel"
        )
    )
    monkeypatch.setattr("loadtest.runtime.subprocess.run", runner)
    monkeypatch.setattr("loadtest.runtime.shutil.which", Mock(return_value="/usr/bin/docker"))

    with pytest.raises(RuntimeError, match="output suppressed") as error:
        compose("exec", "gateway-loadtest-1", "gateway-admin", "create-key")

    assert "secret sentinel" not in str(error.value)


def test_private_write_has_private_permissions_and_cannot_replace_files(tmp_path: Path) -> None:
    path = tmp_path / "key"

    private_write(path, "synthetic")

    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        private_write(path, "replacement")
    assert path.read_text() == "synthetic"


def test_only_k6_threshold_exit_can_be_preserved_as_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = Mock(return_value=subprocess.CompletedProcess([], 99, stdout="thresholds", stderr=""))
    monkeypatch.setattr("loadtest.runtime.subprocess.run", runner)
    monkeypatch.setattr("loadtest.runtime.shutil.which", Mock(return_value="/usr/bin/docker"))

    assert compose("run", "k6", allow_failure=True) == "thresholds"
    runner.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
    with pytest.raises(RuntimeError, match="exit 1"):
        compose("run", "k6", allow_failure=True)
