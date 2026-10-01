"""Exercise the parent lifecycle and child credential boundaries, not just helpers."""

from unittest.mock import Mock

import pytest

from deploy.demo import supervisor
from deploy.demo.processes import Child
from tests.demo.fixtures import demo_environment


def test_running_parent_exits_nonzero_and_shuts_down_if_a_child_exits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    child = Mock(poll=Mock(return_value=0))

    def start(env: dict[str, str], children: list[Child], stopped: object) -> None:
        children.append(("console", child))

    monkeypatch.setattr(supervisor, "appliance_environment", demo_environment)
    monkeypatch.setattr(supervisor, "_start_children", start)
    monkeypatch.setattr(supervisor, "signal", Mock())
    monkeypatch.setattr(supervisor, "resource", Mock())
    shutdown = Mock()
    monkeypatch.setattr(supervisor, "shutdown", shutdown)

    assert supervisor.main() == 1

    shutdown.assert_called_once_with([("console", child)])
    assert "child exited: console" in capsys.readouterr().err


def test_boot_credentials_reach_only_the_relevant_child_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = {
        "DEMO_VIEWER_KEY": "synthetic-platform-boot-key",
        "DEMO_ORG_VIEWER_KEY": "synthetic-org-boot-key",
        "DEMO_TENANT_KEY": "synthetic-traffic-boot-key",
    }
    bootstrap = Mock(side_effect=[{}, issued])
    launch = Mock(return_value=("unused", Mock(poll=Mock(return_value=None))))
    monkeypatch.setattr(supervisor, "bootstrap", bootstrap)
    monkeypatch.setattr(supervisor, "launch", launch)
    monkeypatch.setattr(supervisor, "wait_http", Mock())
    env = {
        **demo_environment(),
        "PORT": "3000",
        "ADMIN_API_URL": "http://127.0.0.1:18091",
        "DEMO_TRAFFIC_WINDOW_S": "120",
    }
    monkeypatch.setattr(supervisor, "appliance_environment", Mock(return_value=env))
    monkeypatch.setattr(supervisor, "ensure_alive", Mock(side_effect=[None, RuntimeError("done")]))
    monkeypatch.setattr(supervisor, "signal", Mock())
    monkeypatch.setattr(supervisor, "resource", Mock())
    monkeypatch.setattr(supervisor, "shutdown", Mock())

    assert supervisor.main() == 1

    calls = {call.args[0]: call.args[2] for call in launch.call_args_list}
    for name in ("fake-provider", "gateway"):
        assert not issued.keys() & calls[name].keys()
    assert calls["console"]["DEMO_VIEWER_KEY"] == issued["DEMO_VIEWER_KEY"]
    assert calls["console"]["DEMO_ORG_VIEWER_KEY"] == issued["DEMO_ORG_VIEWER_KEY"]
    assert "DEMO_TENANT_KEY" not in calls["console"]
    assert "DATABASE_URL" not in calls["console"]
    assert calls["traffic"]["DEMO_TENANT_KEY"] == issued["DEMO_TENANT_KEY"]
    assert calls["traffic"]["DEMO_TRAFFIC_WINDOW_S"] == "120"
    assert (
        not {"DEMO_VIEWER_KEY", "DEMO_ORG_VIEWER_KEY", "GATEWAY_API_KEY_PEPPER"}
        & calls["traffic"].keys()
    )
