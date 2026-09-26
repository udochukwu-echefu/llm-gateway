"""Resolve deployment secrets without making callers know their storage location."""

import os
import stat
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr


class SecretStore(Protocol):
    def get(self, name: str) -> SecretStr | None: ...


class EnvSecretStore:
    def __init__(self, fallbacks: dict[str, SecretStr | None] | None = None) -> None:
        # Settings loads .env for local development; the store remains the only
        # interface that exposes those values to the running application.
        self.fallbacks = fallbacks or {}

    def get(self, name: str) -> SecretStr | None:
        value = os.environ.get(f"GATEWAY_{name.upper()}")
        return SecretStr(value) if value is not None else self.fallbacks.get(name)


class FileSecretStore:
    def __init__(self, directory: Path) -> None:
        self._check_mode(directory)
        if not directory.is_dir():
            raise ValueError("Secrets path must be a directory")
        self.directory = directory.resolve(strict=True)

    @staticmethod
    def _check_mode(path: Path) -> None:
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError("Secrets directory and files must not be accessible by others")

    def get(self, name: str) -> SecretStr | None:
        # Callers use fixed names; still prohibit traversal for future store users.
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Invalid secret name")
        path = self.directory / name
        try:
            target = path.resolve(strict=True)
        except FileNotFoundError:
            if path.is_symlink():
                raise ValueError("Secret symlink target does not exist") from None
            return None
        if not target.is_relative_to(self.directory):
            raise ValueError("Secret symlink target must remain inside secrets directory")
        self._check_mode(target)
        if not target.is_file():
            raise ValueError("Secret must be a regular file")
        value = target.read_text()
        return SecretStr(value.removesuffix("\n"))
