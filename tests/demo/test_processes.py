"""Real subprocess output must survive startup failure without publishing credentials."""

import os
import sys
from pathlib import Path
from threading import Event

import pytest

from deploy.demo import supervisor
from deploy.demo.output import drain_output
from deploy.demo.processes import Child, launch, shutdown
from tests.demo.fixtures import demo_environment


def test_child_stdout_and_stderr_reach_matching_supervisor_streams(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    child = launch(
        "gateway",
        [sys.executable, "-c", "import sys; print('ready'); print('warning', file=sys.stderr)"],
        {},
        cwd=str(tmp_path),
    )
    child[1].wait(timeout=10)
    drain_output(child[1])

    captured = capsys.readouterr()
    assert captured.out == "[gateway] ready\n"
    assert captured.err == "[gateway] warning\n"


def test_child_output_is_forwarded_while_it_is_still_running(tmp_path: Path) -> None:
    class ObservedOutput:
        def write(self, value: str) -> int:
            if "ready" in value:
                observed.set()
            return len(value)

        def flush(self) -> None:
            pass

    observed = Event()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "stdout", ObservedOutput())
        child = launch(
            "gateway",
            [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
            {},
            cwd=str(tmp_path),
        )
        try:
            assert observed.wait(timeout=10)
            assert child[1].poll() is None
        finally:
            shutdown([child])


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_forwarded_output_masks_key_shapes_and_credential_urls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stream: str
) -> None:
    line = (
        "lgw_abcdefghijkl_synthetic-tenant_key lgwa_abcdefghijkl_synthetic-admin_key "
        "postgres://user:synthetic-db-password@db.invalid/demo "
        "postgresql+asyncpg://user:encoded%40password@db.invalid/demo?ssl=require "
        "redis://:synthetic-redis-password@cache.invalid/15 "
        "rediss://default:synthetic-tls-password@cache.invalid/0"
    )
    child = launch(
        "gateway",
        [sys.executable, "-c", f"import sys; print({line!r}, file=sys.{stream})"],
        {},
        cwd=str(tmp_path),
    )
    child[1].wait(timeout=10)
    drain_output(child[1])

    captured = capsys.readouterr()
    output = captured.out if stream == "stdout" else captured.err
    assert output.startswith("[gateway] ")
    assert output.count("[redacted]") == 6
    assert "lgw_" not in output
    assert "lgwa_" not in output
    assert all(
        value not in output
        for value in (
            "synthetic-db-password",
            "encoded%40password",
            "synthetic-redis-password",
            "synthetic-tls-password",
            "synthetic-tenant_key",
            "synthetic-admin_key",
        )
    )
    assert "db.invalid/demo" in output
    assert "cache.invalid/15" in output


def test_crashing_child_final_lines_precede_supervisor_exit_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def start(env: dict[str, str], children: list[Child], stopped: object) -> None:
        child = launch(
            "gateway",
            [
                sys.executable,
                "-c",
                "import sys; print('last diagnostic', file=sys.stderr); sys.exit(1)",
            ],
            {},
            cwd=str(tmp_path),
        )
        children.append(child)
        child[1].wait(timeout=10)

    monkeypatch.setattr(supervisor, "appliance_environment", demo_environment)
    monkeypatch.setattr(supervisor, "_start_children", start)

    assert supervisor.main() == 1

    output = capsys.readouterr().err
    assert output.index("[gateway] last diagnostic") < output.index("Appliance child exited")


def test_boot_helper_output_is_forwarded_but_boot_pipe_stays_private(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def boot_launch(
        name: str, args: list[str], env: dict[str, str], *, pass_fds: tuple[int, ...]
    ) -> Child:
        script = (
            "import os, sys; print('preparing'); print('diagnostic', file=sys.stderr); "
            "os.write(int(os.environ['DEMO_BOOT_KEY_FD']), b'{\"key\":\"synthetic-private-pipe\"}')"
        )
        return launch(
            name, [sys.executable, "-c", script], env, cwd=str(tmp_path), pass_fds=pass_fds
        )

    monkeypatch.setattr(supervisor, "launch", boot_launch)

    assert supervisor.bootstrap({"PATH": os.environ.get("PATH", "")}, "prepare", lambda: False) == {
        "key": "synthetic-private-pipe"
    }

    captured = capsys.readouterr()
    assert "[bootstrap-prepare] preparing" in captured.out
    assert "[bootstrap-prepare] diagnostic" in captured.err
    assert "synthetic-private-pipe" not in captured.out + captured.err
