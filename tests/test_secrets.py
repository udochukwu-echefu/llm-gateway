import os
from pathlib import Path

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


def test_file_store_accepts_kubernetes_atomic_symlink_layout(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    version = directory / "..2026_09_26"
    version.mkdir(mode=0o700)
    (version / "api_key_pepper").write_text("fake-mounted-secret\n")
    (version / "api_key_pepper").chmod(0o400)
    (directory / "..data").symlink_to(version.name, target_is_directory=True)
    (directory / "api_key_pepper").symlink_to("..data/api_key_pepper")

    result = FileSecretStore(directory).get("api_key_pepper")

    assert result == SecretStr("fake-mounted-secret")


def test_file_store_rejects_symlink_escaping_secrets_directory(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_text("fake-outside-value")
    outside.chmod(0o400)
    (directory / "api_key_pepper").symlink_to(outside)

    with pytest.raises(ValueError, match="must remain inside"):
        FileSecretStore(directory).get("api_key_pepper")


def test_file_store_checks_symlink_targets_permissions(tmp_path: Path) -> None:
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    target = directory / "..2026_09_26"
    target.mkdir(mode=0o700)
    (target / "database_url").write_text("fake-database-url")
    (target / "database_url").chmod(0o644)
    (directory / "database_url").symlink_to(target / "database_url")

    with pytest.raises(ValueError, match="accessible by others"):
        FileSecretStore(directory).get("database_url")


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
