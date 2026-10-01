from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

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

from llm_gateway.observability.configuration import MetricsSettings, TracingSettings
from llm_gateway.providers.defaults import DEFAULT_BASE_URLS, DEFAULT_READ_TIMEOUTS
from llm_gateway.providers.timeouts import ProviderTimeouts
from llm_gateway.resilience.configuration import ResilienceSettings
from llm_gateway.schemas.common import ProviderName


class ProviderSettings(BaseModel):
    """Optional phase overrides are resolved alongside the global timeouts."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    api_key: SecretStr | None = None
    base_url: HttpUrl | None = None
    connect_timeout_s: float | None = Field(default=None, gt=0)
    read_timeout_s: float | None = Field(default=None, gt=0)
    write_timeout_s: float | None = Field(default=None, gt=0)
    pool_timeout_s: float | None = Field(default=None, gt=0)

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
    zai: ProviderSettings = Field(default_factory=ProviderSettings)
    nvidia: ProviderSettings = Field(default_factory=ProviderSettings)

    def enabled(self) -> list[tuple[ProviderName, ProviderSettings]]:
        return [
            (name, block)
            for name in DEFAULT_BASE_URLS
            if (block := getattr(self, name)).api_key is not None
        ]


class SecretsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["env", "file"] = "env"
    dir: Path | None = None

    @model_validator(mode="after")
    def _file_needs_directory(self) -> Self:
        if self.backend == "file" and self.dir is None:
            raise ValueError("GATEWAY_SECRETS__DIR is required for file backend")
        return self


class LimitsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_rpm: int = Field(default=0, ge=0)
    rpm_burst: int | None = Field(default=None, ge=1)
    default_tpm: int = Field(default=0, ge=0)
    default_max_concurrency: int = Field(default=0, ge=0)
    default_monthly_budget_usd: Decimal = Field(
        default=Decimal(0), ge=0, le=Decimal("9223372.036854775807"), decimal_places=12
    )
    default_alert_threshold: Decimal = Field(default=Decimal("0.8"), gt=0, le=1)
    ip_failures_per_minute: int = Field(default=20, gt=0)
    lease_ttl_s: int = Field(default=900, gt=0)
    redis_timeout_s: float = Field(default=0.05, gt=0)
    budget_rebuild_timeout_s: float = Field(default=0.2, gt=0)
    budget_reconcile_interval_s: float = Field(default=300, gt=0)
    fail_mode: Literal["open", "closed"] = "open"


class CacheSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    ttl_s: int = Field(default=3600, gt=0, le=7 * 24 * 3600)
    max_entry_bytes: int = Field(default=1024 * 1024, gt=0)


class AdminApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8081, ge=1, le=65535)


class Settings(BaseSettings):
    """Runtime configuration, read from GATEWAY_* environment variables (and `.env` locally).

    Missing or invalid values fail at startup rather than on the first request.
    """

    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_", env_file=".env", extra="ignore", env_nested_delimiter="__"
    )

    providers: ProvidersSettings = Field(default_factory=ProvidersSettings)
    secrets: SecretsSettings = Field(default_factory=SecretsSettings)
    api_key_pepper: SecretStr | None = None
    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    cache_encryption_key: SecretStr | None = None
    cache: CacheSettings = Field(default_factory=CacheSettings)
    admin_api: AdminApiSettings = Field(default_factory=AdminApiSettings)
    demo_deployment: bool = False
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    trusted_proxy_hops: int = Field(default=0, ge=0)
    key_cache_ttl_s: float = Field(default=30, ge=0)
    key_cache_max_size: int = Field(default=10_000, ge=0)
    usage_queue_size: int = Field(default=10_000, gt=0)
    usage_batch_size: int = Field(default=500, gt=0)
    usage_flush_interval_s: float = Field(default=1.0, gt=0)
    usage_shutdown_timeout_s: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def _has_provider(self) -> Self:
        if self.secrets.backend == "env" and not self.providers.enabled():
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

    @model_validator(mode="after")
    def _lease_outlasts_provider_stall(self) -> Self:
        self.validate_provider_timeouts()
        return self

    def provider_timeouts(self, name: ProviderName, block: ProviderSettings) -> ProviderTimeouts:
        """Explicit overrides win; NVIDIA alone has a reviewed longer read default."""
        return ProviderTimeouts(
            connect=block.connect_timeout_s or self.connect_timeout_s,
            read=block.read_timeout_s or DEFAULT_READ_TIMEOUTS.get(name, self.read_timeout_s),
            write=block.write_timeout_s or self.write_timeout_s,
            pool=block.pool_timeout_s or self.pool_timeout_s,
        )

    def validate_provider_timeouts(self) -> None:
        """Recheck after secret-store resolution reveals which providers are enabled."""
        enabled = self.providers.enabled()
        if not enabled:
            return  # File-backed keys are checked after resolution in create_app.
        name, block = max(enabled, key=lambda pair: self.provider_timeouts(*pair).combined)
        combined = self.provider_timeouts(name, block).combined
        if self.limits.lease_ttl_s <= combined:
            raise ValueError(
                f"Lease TTL must exceed combined provider timeouts for enabled provider '{name}' "
                f"({combined:g} s); GATEWAY_LIMITS__LEASE_TTL_S={self.limits.lease_ttl_s}"
            )

    @model_validator(mode="after")
    def _demo_provider_guard(self) -> Self:
        self.validate_demo_providers()
        return self

    def validate_demo_providers(self) -> None:
        """Demo URLs are an exact service allowlist, never arbitrary private hosts."""
        if not self.demo_deployment:
            return
        for block in vars(self.providers).values():
            if block.api_key is None and block.base_url is None:
                continue
            if block.base_url is None or str(block.base_url).rstrip("/") != (
                "http://127.0.0.1:18000/v1"
            ):
                raise ValueError("Demo deployment permits only http://127.0.0.1:18000/v1")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_ADMIN_", extra="ignore")
    actor: str | None = Field(default=None, min_length=1)
