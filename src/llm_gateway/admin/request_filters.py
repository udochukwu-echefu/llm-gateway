"""Strict query contracts; timestamps require an explicit zone."""

import base64
import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    since: datetime | None = None
    until: datetime | None = None
    team: str | None = Field(default=None, min_length=1, max_length=256)
    key_id: str | None = Field(default=None, pattern=r"^[a-z2-7]{12}$")
    provider: Literal["groq", "deepseek", "gemini", "openai", "zai", "nvidia"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=256)
    alias: str | None = Field(default=None, min_length=1, max_length=32)
    endpoint: Literal["chat", "embeddings"] | None = None
    status: str | None = Field(default=None, pattern=r"^(?:[245]xx|[1-5][0-9]{2})$")
    outcome: (
        Literal[
            "success",
            "upstream_error",
            "client_disconnected",
            "stream_error",
            "gateway_error",
            "cache_hit",
        ]
        | None
    ) = None
    cost_status: (
        Literal["priced", "unpriced", "usage_missing", "stream_incomplete", "not_billed", "cached"]
        | None
    ) = None
    stream: bool | None = None
    cache_hit: bool | None = None
    redacted: bool | None = None
    fallback: bool | None = None
    retried: bool | None = None
    min_latency: float | None = Field(default=None, ge=0)
    cursor: str | None = Field(default=None, max_length=512)
    page_size: int = Field(default=50, ge=1, le=200)

    @field_validator("stream", "cache_hit", "redacted", "fallback", "retried", mode="before")
    @classmethod
    def boolean(cls, value: object) -> object:
        if value not in ("true", "false", True, False):
            raise ValueError("Boolean filters must be true or false")
        return value

    @field_validator("since", "until")
    @classmethod
    def zoned(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamp needs a zone")
        return value

    @model_validator(mode="after")
    def ordered(self) -> "RequestFilters":
        if self.since and self.until and self.since > self.until:
            raise ValueError("since must be before until")
        return self


def query_values(request: Request) -> dict[str, str]:
    if len(request.query_params) != len(request.query_params.multi_items()):
        raise ValueError("Duplicate filter")
    return dict(request.query_params)


def encode_cursor(created: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([created.isoformat(), str(row_id)]).encode()
    ).decode()


def decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        created, row_id = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        timestamp = datetime.fromisoformat(created)
        if timestamp.tzinfo is None:
            raise ValueError("Missing zone")
        return timestamp, uuid.UUID(row_id)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Invalid request cursor") from exc
