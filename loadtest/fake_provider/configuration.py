"""Fail startup rather than silently benchmarking a mistyped delay."""

import os

from pydantic import BaseModel, Field


class FakeSettings(BaseModel):
    latency_ms: float = Field(default=200, ge=0, le=60000)
    chunk_count: int = Field(default=20, ge=1, le=1000)
    chunk_interval_ms: float = Field(default=50, ge=0, le=60000)

    @classmethod
    def from_environment(cls) -> "FakeSettings":
        return cls.model_validate(
            {
                "latency_ms": os.getenv("FAKE_LATENCY_MS", "200"),
                "chunk_count": os.getenv("FAKE_CHUNK_COUNT", "20"),
                "chunk_interval_ms": os.getenv("FAKE_CHUNK_INTERVAL_MS", "50"),
            }
        )
