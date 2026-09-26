import os

import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from llm_gateway.secrets import EnvSecretStore, FileSecretStore
from tests.conftest import TEST_DATABASE_URL, TEST_PEPPER


def test_env_store_reads_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_TEST_SECRET", "fake-env-secret")

    assert EnvSecretStore().get("test_secret") == SecretStr("fake-env-secret")
    assert EnvSecretStore().get("absent_secret") is None


def test_file_store_strips_one_newline_and_returns_none_for_missing(
    tmp_path: os.PathLike[str],
) -> None:
    from pathlib import Path

    directory = Path(tmp_path)
    directory.chmod(0o700)
    (directory / "example").write_text("fake-file-secret\n\n")
    (directory / "example").chmod(0o600)

    store = FileSecretStore(directory)

    assert store.get("example") == SecretStr("fake-file-secret\n")
    assert store.get("missing") is None


@pytest.mark.parametrize("target", ["directory", "file"])
def test_file_store_rejects_permissions_readable_by_others(
    tmp_path: os.PathLike[str], target: str
) -> None:
    from pathlib import Path

    directory = Path(tmp_path)
    directory.chmod(0o700)
    path = directory / "secret"
    path.write_text("fake-secret")
    path.chmod(0o600)
    if target == "directory":
        directory.chmod(0o755)
        with pytest.raises(ValueError, match="accessible by others"):
            FileSecretStore(directory)
    else:
        path.chmod(0o644)
        with pytest.raises(ValueError, match="accessible by others"):
            FileSecretStore(directory).get("secret")


@pytest.mark.parametrize("missing", ["pepper", "database", "short_pepper"])
def test_startup_rejects_missing_or_short_critical_secrets(
    settings: Settings, missing: str
) -> None:
    class IncompleteStore:
        def get(self, name: str) -> SecretStr | None:
            if name == "api_key_pepper":
                return (
                    None
                    if missing == "pepper"
                    else SecretStr("short" if missing == "short_pepper" else TEST_PEPPER)
                )
            if name == "database_url":
                return None if missing == "database" else SecretStr(TEST_DATABASE_URL)
            return None

    # File mode does not silently fall back to settings or process environment.
    configured = settings.model_copy(
        update={"secrets": settings.secrets.model_copy(update={"backend": "file"})}
    )
    with pytest.raises(ValueError, match=r"PEPPER|DATABASE_URL"):
        create_app(configured, secret_store=IncompleteStore())


def test_file_backend_resolves_provider_keys_from_store(settings: Settings) -> None:
    class Store:
        def get(self, name: str) -> SecretStr | None:
            values = {
                "api_key_pepper": TEST_PEPPER,
                "database_url": TEST_DATABASE_URL,
                "providers__groq__api_key": "fake-file-provider-key",
            }
            return SecretStr(values[name]) if name in values else None

    configured = settings.model_copy(
        update={"secrets": settings.secrets.model_copy(update={"backend": "file"})}
    )

    app: FastAPI = create_app(configured, secret_store=Store())

    assert [name for name, _ in app.state.settings.providers.enabled()] == ["groq"]
