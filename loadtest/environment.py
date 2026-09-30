"""Record version metadata only: never inspect container environment or owner secrets."""

import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

from loadtest.runtime import ROOT


def environment() -> dict[str, object]:
    return {
        "tooling_commit": _git("rev-parse", "HEAD"),
        "app_main_commit": _git("rev-parse", "main"),
        "app_source_sha256": source_hash(ROOT / "src"),
        "catalog_sha256": hashlib.sha256((ROOT / "catalog/models.toml").read_bytes()).hexdigest(),
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "host_os": platform.platform(),
        "host_architecture": platform.machine(),
        "python": platform.python_version(),
        "images": {
            "gateway": "llm-gateway:loadtest (repo Dockerfile)",
            "k6": "grafana/k6:1.3.0",
            "nginx": "nginx:1.28.0-alpine",
            "postgres": "postgres:17.6",
            "redis": "redis:7.4.5",
            "prometheus": "prom/prometheus:v3.2.1",
            "py_spy": "0.4.2 (diagnostic only)",
        },
        "sampling": {"prometheus_s": 1, "queue_s": 2, "container_s": 5},
    }


def source_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git(*arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        return "unavailable"
    result = subprocess.run(  # noqa: S603 -- fixed read-only git argv, no shell
        [executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    print(json.dumps(environment(), indent=2))
