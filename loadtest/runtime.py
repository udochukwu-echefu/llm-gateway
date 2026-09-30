"""Run only the fake-provider profile, ignoring the owner's .env and gateway variables."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "loadtest" / ".state"
RESULTS = ROOT / "loadtest" / "results"
REPLICAS = ("gateway-loadtest-1", "gateway-loadtest-2")


def compose(*arguments: str, latency_ms: int = 200, allow_failure: bool = False) -> str:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("GATEWAY_", "FAKE_", "COMPOSE_", "PROMETHEUS_", "LOADTEST_"))
    }
    environment.update(
        PROMETHEUS_CONFIG_DIR="./loadtest/prometheus",
        FAKE_LATENCY_MS=str(latency_ms),
        LOADTEST_UID=str(os.getuid()),
        LOADTEST_GID=str(os.getgid()),
    )
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker executable not found")
    result = subprocess.run(  # noqa: S603 -- fixed executable, argv only, no shell
        [docker, "compose", "--env-file", "/dev/null", "--profile", "loadtest", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    # k6's 99 means threshold failure, whose measurements must remain available.
    if result.returncode and (not allow_failure or result.returncode != 99):
        raise RuntimeError(
            f"load-test Docker command failed (exit {result.returncode}); output suppressed"
        )
    return result.stdout


def private_write(path: Path, value: str) -> None:
    """Exclusive creation prevents following a planted symlink or replacing user files."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(value)


def prepare_directories() -> None:
    for directory in (STATE, RESULTS):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_mode & 0o077:
            raise ValueError("Load-test state/results directories must be private (mode 0700)")
