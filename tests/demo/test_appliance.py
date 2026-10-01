"""Portable appliance boundaries tested without Docker or real provider connections."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from deploy.demo.boot_keys import send_boot_keys
from deploy.demo.config import appliance_environment, normalize_database_url
from deploy.demo.processes import Child, ensure_alive, shutdown
from deploy.demo.supervisor import internal_command
from llm_gateway.config import Settings
from tests.demo.fixtures import demo_environment


def test_appliance_internal_listeners_bind_only_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in appliance_environment(demo_environment()).items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime env config

    assert settings.admin_api.host == "127.0.0.1"
    assert settings.metrics.host == "127.0.0.1"
    assert settings.demo_deployment
    assert settings.tracing.otlp_endpoint is None
    assert internal_command("llm_gateway.main:create_app", "18090")[6] == "127.0.0.1"
    assert all(
        str(block.base_url) == "http://127.0.0.1:18000/v1"
        for _, block in settings.providers.enabled()
    )


@pytest.mark.parametrize(
    "override",
    [
        {"PORT": "8080"},
        {"PORT": "synthetic-secret"},
        {"DATABASE_URL": "invalid-secret"},
        {"REDIS_URL": "http://invalid-secret"},
        {"GATEWAY_ADMIN_API__HOST": "0.0.0.0"},  # noqa: S104 -- rejected unsafe configuration
        {"GATEWAY_PROVIDERS__OPENAI__BASE_URL": "https://api.openai.com/v1"},
        {"GATEWAY_PROVIDERS": '{"openai":{"base_url":"https://invalid-secret"}}'},
        {"GATEWAY_API_KEY_PEPPER": "short-secret"},
        {"GATEWAY_CACHE_ENCRYPTION_KEY": "invalid-secret"},
        {"ADMIN_CONSOLE_ORIGIN": "https://invalid-secret/path"},
    ],
)
def test_appliance_rejects_unsafe_config_without_echoing_values(override: dict[str, str]) -> None:
    with pytest.raises(ValueError, match=r".") as error:
        appliance_environment({**demo_environment(), **override})
    assert not any(value in str(error.value) for value in override.values())


def test_managed_postgres_binding_translates_sslmode() -> None:
    assert normalize_database_url("postgres://demo:fake@db.fake.invalid/demo?sslmode=require") == (
        "postgresql+asyncpg://demo:fake@db.fake.invalid/demo?ssl=require"
    )


def test_appliance_fixed_idle_intervals_override_short_inherited_timers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = appliance_environment(
        {
            **demo_environment(),
            "GATEWAY_LIMITS__BUDGET_RECONCILE_INTERVAL_S": "1",
            "GATEWAY_USAGE_FLUSH_INTERVAL_S": "1",
            "GATEWAY_USAGE_BATCH_SIZE": "500",
            "GATEWAY_TRACING__OTLP_ENDPOINT": "https://fake.invalid",
            "NEXT_TELEMETRY_DISABLED": "0",
        }
    )
    intervals = {
        "GATEWAY_LIMITS__BUDGET_RECONCILE_INTERVAL_S": "3600",
        "GATEWAY_USAGE_FLUSH_INTERVAL_S": "3600",
    }
    assert {name: value for name, value in env.items() if name.endswith("_INTERVAL_S")} == intervals
    assert all(int(value) >= 1800 for value in intervals.values())
    assert env["DEMO_TRAFFIC_WINDOW_S"] == "600"
    assert env["GATEWAY_USAGE_BATCH_SIZE"] == "1"
    assert env["NEXT_TELEMETRY_DISABLED"] == "1"
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]  # runtime env config

    assert settings.limits.budget_reconcile_interval_s == 3600
    assert settings.usage_flush_interval_s == 3600
    assert settings.usage_batch_size == 1
    assert settings.tracing.otlp_endpoint is None


def test_appliance_preserves_configurable_traffic_window() -> None:
    env = appliance_environment({**demo_environment(), "DEMO_TRAFFIC_WINDOW_S": "120"})

    assert env["DEMO_TRAFFIC_WINDOW_S"] == "120"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "1.5", "synthetic-secret"])
def test_appliance_rejects_invalid_traffic_window_without_echoing_it(value: str) -> None:
    with pytest.raises(ValueError, match="Demo traffic window must be a positive integer") as error:
        appliance_environment({**demo_environment(), "DEMO_TRAFFIC_WINDOW_S": value})

    assert value not in str(error.value)


def test_only_successfully_completed_traffic_child_may_exit() -> None:
    traffic = Mock(poll=Mock(return_value=0))
    console = Mock(poll=Mock(return_value=None))

    ensure_alive([("traffic", traffic), ("console", console)])
    traffic.poll.return_value = 1
    with pytest.raises(RuntimeError, match="child exited: traffic"):
        ensure_alive([("traffic", traffic), ("console", console)])


def test_boot_keys_use_only_private_pipe_never_stdout_or_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    keys = {"DEMO_VIEWER_KEY": "synthetic-boot-key-sentinel"}
    reader, writer = os.pipe()
    try:
        send_boot_keys(keys, writer)
        assert json.loads(os.read(reader, 4096)) == keys
    finally:
        os.close(reader)
        os.close(writer)
    captured = capfd.readouterr()
    assert "synthetic-boot-key-sentinel" not in captured.out + captured.err
    assert list(tmp_path.iterdir()) == []
    for descriptor in (1, 2):
        with pytest.raises(ValueError, match="private pipe"):
            send_boot_keys(keys, descriptor)
    with (
        (tmp_path / "not-a-pipe").open("wb") as file,
        pytest.raises(ValueError, match="private pipe"),
    ):
        send_boot_keys(keys, file.fileno())


def test_child_exit_fails_appliance() -> None:
    child = Mock()
    child.poll.return_value = 0
    with pytest.raises(RuntimeError, match="child exited: console"):
        ensure_alive([("console", child)])


def test_shutdown_orders_console_gateway_then_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[int] = []
    children: list[Child] = []
    for name, pid in (("fake-provider", 4), ("gateway", 3), ("console", 2), ("traffic", 1)):
        child = Mock(pid=pid)
        child.poll.return_value = None
        children.append((name, child))

    def killpg(pid: int, signum: int) -> None:
        events.append(pid)

    monkeypatch.setattr(os, "killpg", killpg)

    shutdown(children)

    assert events == [1, 2, 3, 4]


def test_hung_console_is_killed_without_using_gateways_flush_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console = Mock(pid=10, poll=Mock(return_value=None))
    console.wait.side_effect = [subprocess.TimeoutExpired("console", 4), 0]
    gateway = Mock(pid=11, poll=Mock(return_value=None))
    monkeypatch.setattr("deploy.demo.processes.time", Mock(monotonic=Mock(return_value=0)))
    signals: list[tuple[int, int]] = []

    def killpg(pid: int, signum: int) -> None:
        signals.append((pid, signum))

    monkeypatch.setattr(os, "killpg", killpg)

    shutdown([("console", console), ("gateway", gateway)])

    assert [pid for pid, _ in signals] == [10, 10, 11]
    assert console.wait.call_args_list[0].kwargs["timeout"] <= 4
    assert gateway.wait.call_args.kwargs["timeout"] == 12


def test_shutdown_tolerates_a_child_exiting_between_poll_and_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = Mock(pid=10, poll=Mock(return_value=None))
    monkeypatch.setattr(os, "killpg", Mock(side_effect=ProcessLookupError))

    shutdown([("console", child)])

    child.wait.assert_called_once()


def test_local_profile_publishes_only_console() -> None:
    compose = Path("deploy/demo/compose.yaml").read_text()
    assert compose.count("ports:") == 1
    assert "127.0.0.1:${CONSOLE_TEST_PORT:-3300}:3000" in compose
    dockerfile = Path("deploy/demo/Dockerfile").read_text()
    assert "USER demo" in dockerfile
    assert "EXPOSE 3000\n" in dockerfile
    assert "latest" not in dockerfile


def test_secret_provisioning_uses_stdin_not_arguments_files_or_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from deploy.demo.set_secrets import set_secrets

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("deploy.demo.set_secrets.shutil.which", Mock(return_value="/fake/insta"))
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr("deploy.demo.set_secrets.subprocess.run", run)

    set_secrets()

    captured = capsys.readouterr()
    assert run.call_count == 3
    for call in run.call_args_list:
        value = call.kwargs["input"].decode()
        assert value not in repr(call.args) + captured.out + captured.err
        assert call.kwargs["stdout"] == call.kwargs["stderr"] == subprocess.DEVNULL
    assert list(tmp_path.iterdir()) == []
