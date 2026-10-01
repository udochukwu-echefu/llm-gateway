"""Stdlib process supervision: redacted child output, bounded readiness and ordered shutdown."""

import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress

from deploy.demo.output import drain_output, forward_output

Child = tuple[str, subprocess.Popen[bytes]]


def launch(
    name: str,
    args: list[str],
    env: dict[str, str],
    *,
    cwd: str = "/app",
    pass_fds: tuple[int, ...] = (),
) -> Child:
    process = subprocess.Popen(  # noqa: S603 -- fixed appliance commands
        args,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=pass_fds,
        start_new_session=True,
    )
    forward_output(name, process)
    return name, process


def ensure_alive(children: list[Child]) -> None:
    for name, process in children:
        status = process.poll()
        # Traffic is a bounded boot job, not a required long-lived server. Never restart it.
        if name == "traffic" and status == 0:
            continue
        if status is not None:
            drain_output(process)
            raise RuntimeError(f"Appliance child exited: {name}.")


def wait_http(
    url: str, children: list[Child], stopped: Callable[[], bool], timeout: float = 30
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not stopped():
        ensure_alive(children)
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310 -- fixed localhost URLs only
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Appliance readiness timed out.")


def shutdown(children: list[Child], timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    # Traffic stops first, console second, gateway flushes before the fake upstream stops.
    priorities = {"traffic": 0, "console": 1, "gateway": 2, "fake-provider": 3}
    grace = {"traffic": 1, "console": 4, "gateway": 12, "fake-provider": 2}
    for name, process in sorted(children, key=lambda child: priorities[child[0]]):
        if process.poll() is not None:
            drain_output(process, timeout=max(0, min(2, deadline - time.monotonic())))
            continue
        _signal_group(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=max(0.1, min(grace[name], deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            _signal_group(process.pid, signal.SIGKILL)
            process.wait(timeout=max(0.1, min(1, deadline - time.monotonic())))

        drain_output(process, timeout=max(0, min(2, deadline - time.monotonic())))


def _signal_group(pid: int, signum: int) -> None:
    # A child can exit between poll() and signal delivery.
    with suppress(ProcessLookupError):
        os.killpg(pid, signum)
