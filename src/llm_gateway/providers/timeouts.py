"""Resolved pool timeouts shared by client construction and lease validation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderTimeouts:
    connect: float
    read: float
    write: float
    pool: float

    @property
    def combined(self) -> float:
        return self.connect + self.read + self.write + self.pool
