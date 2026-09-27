"""Shared, deliberately fake Postgres/CLI setup for database-backed tests."""

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from pydantic import SecretStr

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.tenants.cache import VerifiedKeyCache
from tests.conftest import TEST_PEPPER, OfflineLimitService


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def run_admin(database_url: str, *args: str) -> str:
    result = subprocess.run(  # noqa: S603  # fixed executable; no shell
        [str(Path(__file__).resolve().parents[2] / ".venv/bin/gateway-admin"), *args],
        env={
            **os.environ,
            "GATEWAY_DATABASE_URL": database_url,
            "GATEWAY_API_KEY_PEPPER": TEST_PEPPER,
        },
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class CliKey:
    org: str
    team: str
    full_key: str

    @property
    def key_id(self) -> str:
        return self.full_key.split("_")[1]


def create_cli_key(database_url: str, *, expires_in_days: int | None = None) -> CliKey:
    org = unique_name("cli")
    team = "team"
    run_admin(database_url, "create-org", org)
    run_admin(database_url, "create-team", org, team)
    expiry = ("--expires-in-days", str(expires_in_days)) if expires_in_days else ()
    full_key = run_admin(database_url, "create-key", org, team, "client", *expiry)
    return CliKey(org, team, full_key)


class DatabaseTestStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get(self, name: str) -> SecretStr | None:
        if name == "database_url":
            return SecretStr(self.database_url)
        if name == "api_key_pepper":
            return SecretStr(TEST_PEPPER)
        if name.startswith("providers__") and name.endswith("__api_key"):
            return SecretStr("fake-provider-key")
        return None


def database_app(
    settings: Settings, database_url: str, cache: VerifiedKeyCache | None = None
) -> FastAPI:
    return create_app(
        settings,
        secret_store=DatabaseTestStore(database_url),
        key_cache=cache,
        limit_service=OfflineLimitService(),
    )
