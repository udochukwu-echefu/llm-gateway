from typing import Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_gateway.providers.defaults import DEFAULT_BASE_URLS
from llm_gateway.schemas.common import ProviderName


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    base_url: HttpUrl | None = None

    @field_validator("api_key")
    @classmethod
    def _nonempty_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("API key must be nonempty when set")
        return value

    @field_validator("base_url")
    @classmethod
    def _plain_base_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (value.username or value.password or value.query or value.fragment):
            raise ValueError("base URL must not contain credentials, query or fragment")
        return value


class ProvidersSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groq: ProviderSettings = Field(default_factory=ProviderSettings)
    deepseek: ProviderSettings = Field(default_factory=ProviderSettings)
    gemini: ProviderSettings = Field(default_factory=ProviderSettings)
    openai: ProviderSettings = Field(default_factory=ProviderSettings)

    def enabled(self) -> list[tuple[ProviderName, ProviderSettings]]:
        return [
            (cast(ProviderName, name), block)
            for name in DEFAULT_BASE_URLS
            if (block := getattr(self, name)).api_key is not None
        ]


class Settings(BaseSettings):
    """Runtime configuration, read from GATEWAY_* environment variables (and `.env` locally).

    Missing or invalid values fail at startup rather than on the first request.
    """

    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_", env_file=".env", extra="ignore", env_nested_delimiter="__"
    )

    providers: ProvidersSettings = Field(default_factory=ProvidersSettings)

    @model_validator(mode="after")
    def _has_provider(self) -> Self:
        if not self.providers.enabled():
            raise ValueError("Configure at least one GATEWAY_PROVIDERS__<PROVIDER>__API_KEY")
        return self

    # `read` is the longest silence allowed between two chunks, so it bounds a stalled stream.
    connect_timeout_s: float = Field(default=5.0, gt=0)
    read_timeout_s: float = Field(default=60.0, gt=0)
    write_timeout_s: float = Field(default=10.0, gt=0)
    pool_timeout_s: float = Field(default=5.0, gt=0)
    max_connections: int = Field(default=100, gt=0)
    max_keepalive_connections: int = Field(default=20, ge=0)

    max_request_bytes: int = Field(default=2 * 1024 * 1024, gt=0)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
