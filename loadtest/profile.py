"""Stack-only py-spy sample of a separate S1-shape diagnostic run."""

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from loadtest.run import run_once
from loadtest.runtime import ROOT, compose


def profile() -> None:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker executable not found")
    directory = ROOT / "docs" / "benchmarks"
    directory.mkdir(parents=True, exist_ok=True)
    _docker(docker, "build", "-f", "loadtest/profile.Dockerfile", "-t", "llm-gateway:profile", ".")
    container = compose("ps", "-q", "gateway-loadtest-1").strip()
    baseline = ROOT / "loadtest" / "results" / "S1.json"
    capacity = int(json.loads(baseline.read_text())["median"]["capacity"])
    # A failed first plateau can still be profiled; this is not a new capacity claim.
    rate = capacity or 1
    errors: list[str] = []
    sampler = threading.Thread(target=_record, args=(docker, container, directory, errors))
    sampler.start()
    time.sleep(3)
    result = run_once("profile-S1", rate, 60, 1, 1)
    sampler.join(timeout=90)
    if sampler.is_alive() or errors:
        raise RuntimeError(errors[0] if errors else "py-spy did not finish")
    (directory / "profile-metadata.json").write_text(
        json.dumps(
            {
                "rate": rate,
                "scenario": "S1 diagnostic (not one of capacity repetitions)",
                "measurement": result["artifact"],
                "py_spy": "0.4.2",
                "duration_s": 65,
                "command": (
                    "uvx --offline py-spy record --pid 1 --duration 65 --rate 100 "
                    "--output /profiles/S1-flamegraph.svg"
                ),
            },
            indent=2,
        )
    )


def _record(docker: str, container: str, directory: Path, errors: list[str]) -> None:
    try:
        _docker(
            docker,
            "run",
            "--rm",
            "--pid",
            f"container:{container}",
            "--cap-add",
            "SYS_PTRACE",
            "--security-opt",
            "seccomp=unconfined",
            "--network",
            "none",
            "-v",
            f"{directory}:/profiles",
            "llm-gateway:profile",
            "record",
            "--pid",
            "1",
            "--duration",
            "65",
            "--rate",
            "100",
            "--output",
            "/profiles/S1-flamegraph.svg",
        )
    except RuntimeError as error:
        errors.append(str(error))


def _docker(executable: str, *arguments: str) -> None:
    result = subprocess.run(  # noqa: S603 -- fixed Docker argv, no secret arguments or shell
        [executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"py-spy Docker command failed ({result.returncode}): {result.stderr}")


if __name__ == "__main__":
    profile()
