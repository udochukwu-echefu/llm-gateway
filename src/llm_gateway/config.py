from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from llm_gateway.schemas.common import ProviderName


class Settings(BaseSettings):
    """Runtime configuration, read from GATEWAY_* environment variables (and `.env` locally).

    Missing or invalid values fail at startup rather than on the first request.
    """

    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    # Step 1 forwards to a single OpenAI-compatible provider. Step 3 replaces this with
    # per-provider adapters, and step 4 moves the key into a secret store.
    upstream_provider: ProviderName = "groq"  # decides which provider_options are sent
    upstream_base_url: str = "https://api.groq.com/openai/v1"
    upstream_api_key: SecretStr

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
