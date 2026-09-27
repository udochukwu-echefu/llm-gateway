"""Validated resilience defaults, shared by policy and environment settings."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResilienceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    max_retries: int = Field(default=2, ge=0)
    retry_base_s: float = Field(default=0.25, gt=0)
    retry_cap_s: float = Field(default=2, gt=0)
    retry_read_timeouts: bool = False
    retry_budget_ratio: float = Field(default=0.2, ge=0, le=1)
    retry_window_s: float = Field(default=60, gt=0)
    deadline_s: float = Field(default=60, gt=0)
    breaker_window_s: float = Field(default=30, gt=0)
    breaker_min_calls: int = Field(default=10, gt=0)
    breaker_failure_ratio: float = Field(default=0.5, gt=0, le=1)
    breaker_open_s: float = Field(default=30, gt=0)

    @model_validator(mode="after")
    def _ordered_backoff(self) -> Self:
        if self.retry_base_s > self.retry_cap_s:
            raise ValueError("retry base must not exceed cap")
        return self
