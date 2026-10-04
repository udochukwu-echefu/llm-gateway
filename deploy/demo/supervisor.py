"""One public console listener; all internal processes and boot credentials stay private."""

import json
import os
import re
import resource
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from deploy.demo.config import INTERNAL_HOST, appliance_environment
from deploy.demo.output import drain_output
from deploy.demo.processes import Child, ensure_alive, launch, shutdown, wait_http

BUILD_COMMIT_PATH = Path("/app/build-meta/BUILD_COMMIT")


def bootstrap(env: dict[str, str], stage: str, stopped: Callable[[], bool]) -> dict[str, str]:
    reader, writer = os.pipe()
    try:
        child_env = {**env, "DEMO_BOOT_KEY_FD": str(writer)}
        _, process = launch(
            f"bootstrap-{stage}",
            [sys.executable, "-m", "deploy.demo.prepare", stage],
            child_env,
            pass_fds=(writer,),
        )
        os.close(writer)
        writer = -1
        try:
            status = _wait_boot(process, stopped)
        except RuntimeError:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            drain_output(process)
            raise
        drain_output(process)
        if status != 0:
            raise RuntimeError(
                f"Appliance {stage} failed; check database, Redis and configuration."
            )
        data = os.read(reader, 4096)
        return json.loads(data) if data else {}
    finally:
        os.close(reader)
        if writer != -1:
            os.close(writer)


def main() -> int:
    children: list[Child] = []
    stopped = False

    def stop(signum: int, frame: object) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        env = appliance_environment()
        env.pop("GATEWAY_GIT_COMMIT", None)
        if commit := build_commit(BUILD_COMMIT_PATH):
            env["GATEWAY_GIT_COMMIT"] = commit
        env["DEMO_BOOT_ID"] = uuid.uuid4().hex
        _start_children(env, children, lambda: stopped)
        print("Demo appliance ready.", flush=True)
        while not stopped:
            ensure_alive(children)
            time.sleep(0.2)
        return 0
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    except Exception:
        print(
            "Demo appliance failed; inspect its configuration and service health.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    finally:
        shutdown(children)


def build_commit(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value.lower() if re.fullmatch(r"[0-9a-fA-F]{7,40}", value) else None


def _wait_boot(process: subprocess.Popen[bytes], stopped: Callable[[], bool]) -> int:
    deadline = time.monotonic() + 90
    while not stopped() and time.monotonic() < deadline:
        try:
            return process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
    raise RuntimeError("Appliance boot interrupted or timed out.")


def internal_command(app: str, port: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        app,
        "--factory",
        "--host",
        INTERNAL_HOST,
        "--port",
        port,
        "--no-access-log",
    ]


def _start_children(
    env: dict[str, str], children: list[Child], stopped: Callable[[], bool]
) -> None:
    bootstrap(env, "prepare", stopped)
    children.append(
        launch(
            "fake-provider", internal_command("loadtest.fake_provider.app:create_app", "18000"), env
        )
    )
    children.append(
        launch("gateway", internal_command("llm_gateway.main:create_app", "18090"), env)
    )
    wait_http("http://127.0.0.1:18090/readyz", children, stopped)
    keys = bootstrap(env, "keys", stopped)
    ensure_alive(children)
    console_env = {
        **{
            name: value
            for name, value in env.items()
            if name.startswith("ADMIN_CONSOLE_")
            or name
            in {
                "PATH",
                "HOME",
                "PORT",
                "HOSTNAME",
                "DEMO_MODE",
                "DEMO_ALLOW_KEY_SIGN_IN",
                "ADMIN_API_URL",
                "NEXT_TELEMETRY_DISABLED",
            }
        },
        **{name: value for name, value in keys.items() if name != "DEMO_TENANT_KEY"},
    }
    children.append(
        launch("console", ["node", "scripts/docker-start.mjs"], console_env, cwd="/app/console")
    )
    wait_http(f"http://127.0.0.1:{env['PORT']}/login", children, stopped)
    children.append(
        launch(
            "traffic",
            [sys.executable, "/app/scripts/demo_traffic.py"],
            {
                "PATH": env.get("PATH", ""),
                "PYTHONPATH": "/app",
                "DEMO_TENANT_KEY": keys["DEMO_TENANT_KEY"],
                "DEMO_TRAFFIC_WINDOW_S": env["DEMO_TRAFFIC_WINDOW_S"],
            },
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
