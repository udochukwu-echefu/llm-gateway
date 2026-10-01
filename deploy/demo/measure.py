"""Local-only measurements; operates exclusively on the disposable demo-test profile."""

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request


def docker(*args: str) -> str:
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker is unavailable; no measurements collected.")
    return subprocess.check_output(  # noqa: S603 -- explicit local test commands
        [executable, *args],
        text=True,
        timeout=120,
    ).strip()


def compose(*args: str) -> str:
    return docker("compose", "-f", "deploy/demo/compose.yaml", "--profile", "demo-test", *args)


def start_to_http_200() -> float:
    started = time.monotonic()
    compose("start", "appliance")
    deadline = started + 120
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:3300/login", timeout=1) as response:
                if response.status == 200:
                    return round(time.monotonic() - started, 3)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.1)
    raise RuntimeError("No HTTP 200 within 120 seconds; no cold-start result.")


def main() -> None:
    try:
        compose("up", "-d", "--wait", "postgres", "redis")
        compose("create", "--no-build", "appliance")
        first = start_to_http_200()
        # Existing synthetic history, warm dependencies; all appliance processes cold again.
        compose("stop", "appliance")
        cold = start_to_http_200()
        container = compose("ps", "-q", "appliance")
        time.sleep(65)  # observation interval, not a test's timing assertion
        memory = docker("stats", "--no-stream", "--format", "{{.MemUsage}}", container)
        image = json.loads(
            docker("image", "inspect", "llm-gateway-demo:step16", "--format", "{{json .}}")
        )
        print(
            json.dumps(
                {
                    "first_provision_to_http_200_seconds": first,
                    "cold_process_start_warm_database_seconds": cold,
                    "whole_appliance_memory_after_65_seconds": memory,
                    "image_size_bytes": image["Size"],
                    "architecture": image["Architecture"],
                },
                indent=2,
            )
        )
    finally:
        compose("down", "--volumes")


if __name__ == "__main__":
    main()
