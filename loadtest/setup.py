"""Bootstrap a separate local database and issue test keys through the real admin CLI."""

import base64
import json
import secrets
import uuid
from pathlib import Path

import httpx

from loadtest.runtime import REPLICAS, STATE, compose, prepare_directories, private_write


def setup() -> None:
    prepare_directories()
    runtime = STATE / "runtime.env"
    if not runtime.exists():
        private_write(
            runtime,
            f"GATEWAY_API_KEY_PEPPER={secrets.token_urlsafe(48)}\n"
            f"GATEWAY_CACHE_ENCRYPTION_KEY={base64.b64encode(secrets.token_bytes(32)).decode()}\n",
        )
    elif runtime.is_symlink() or runtime.stat().st_mode & 0o077:
        raise ValueError("Load-test runtime credentials must be a private regular file")
    compose("up", "-d", "postgres", "redis")
    exists = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "gateway",
        "-d",
        "postgres",
        "-Atc",
        "SELECT 1 FROM pg_database WHERE datname = 'gateway_loadtest'",
    )
    if not exists.strip():
        compose("exec", "-T", "postgres", "createdb", "-U", "gateway", "gateway_loadtest")
    compose("build", "gateway-loadtest-1")
    compose("run", "--rm", "--no-deps", REPLICAS[0], "alembic", "upgrade", "head")
    compose("up", "-d", "fake-provider", *REPLICAS, "loadtest-nginx", "prometheus")
    _wait_for_readiness()


def create_team(scenario: str, rpm: int = 0) -> tuple[str, Path]:
    """Fresh organizations isolate policies, caches, counters and accounting for every run."""
    org = f"loadtest-{scenario.lower()}-{uuid.uuid4().hex}"
    team = "benchmark"
    admin("create-org", org)
    admin("create-team", org, team)
    if rpm:
        admin("set-limits", org, team, "--rpm", str(rpm))
    if scenario == "S4":
        admin(
            "set-guardrails",
            org,
            "--action",
            "email=redact",
            "--action",
            "phone=redact",
            "--action",
            "ip_address=redact",
        )
    key_path = STATE / f"{org}.key"
    private_write(key_path, admin("create-key", org, team, "benchmark").strip())
    private_write(STATE / f"{org}.json", json.dumps({"org": org, "team": team}))
    return org, key_path


def admin(*arguments: str) -> str:
    return compose("exec", "-T", REPLICAS[0], "gateway-admin", *arguments)


def _wait_for_readiness() -> None:
    import time

    with httpx.Client(timeout=5) as client:
        for _ in range(60):
            try:
                if all(
                    client.get(f"http://127.0.0.1:{port}/readyz").status_code == 200
                    for port in (18001, 18002)
                ):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
    raise RuntimeError("Load-test replicas did not become ready (60 attempts)")


if __name__ == "__main__":
    setup()
    print("Fake-provider profile ready; credentials stored privately, never printed.")
