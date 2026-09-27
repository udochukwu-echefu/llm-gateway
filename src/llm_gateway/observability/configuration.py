"""Validate observability configuration before binding sockets or exporting data."""

from ipaddress import ip_address

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class MetricsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "127.0.0.1"
    port: int = Field(default=9464, ge=1, le=65535)
    enabled: bool = True

    @field_validator("host")
    @classmethod
    def valid_address(cls, value: str) -> str:
        ip_address(value)
        return value


class TracingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    otlp_endpoint: HttpUrl | None = None
    sample_ratio: float = Field(default=1.0, ge=0, le=1)
    propagate_to_providers: bool = False

    @field_validator("otlp_endpoint")
    @classmethod
    def plain_endpoint(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (value.username or value.password or value.query or value.fragment):
            raise ValueError("OTLP endpoint must not contain credentials, query or fragment")
        return value
