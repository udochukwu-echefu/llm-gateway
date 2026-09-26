from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, Depends, FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_gateway import __version__
from llm_gateway.api import chat, embeddings, health
from llm_gateway.config import Settings
from llm_gateway.errors import GatewayError, gateway_error_handler, http_exception_handler
from llm_gateway.logging import configure_logging
from llm_gateway.middleware import RequestContextMiddleware
from llm_gateway.providers.pools import provider_pools
from llm_gateway.secrets import EnvSecretStore, FileSecretStore, SecretStore
from llm_gateway.tenants.auth import authenticate
from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.repository import KeyRepository, PostgresKeyRepository

log = structlog.get_logger("llm_gateway")


def create_app(
    settings: Settings | None = None,
    key_repository: KeyRepository | None = None,
    secret_store: SecretStore | None = None,
    key_cache: VerifiedKeyCache | None = None,
) -> FastAPI:
    """Build the application. Run with `uvicorn llm_gateway.main:create_app --factory`."""
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]  # values come from env
    configure_logging(settings.log_level, settings.log_format)
    fallbacks: dict[str, SecretStr | None] = {
        "api_key_pepper": settings.api_key_pepper,
        "database_url": settings.database_url,
        **{
            f"providers__{name}__api_key": block.api_key
            for name, block in vars(settings.providers).items()
        },
    }
    store = secret_store or (
        EnvSecretStore(fallbacks)
        if settings.secrets.backend == "env"
        else FileSecretStore(settings.secrets.dir)  # pyright: ignore[reportArgumentType]  # validated by SecretsSettings
    )
    pepper = store.get("api_key_pepper")
    database_url = store.get("database_url")
    if pepper is None or len(pepper.get_secret_value().encode()) < 32:
        raise ValueError("GATEWAY_API_KEY_PEPPER is required and must be at least 32 bytes")
    if database_url is None or not database_url.get_secret_value():
        raise ValueError("GATEWAY_DATABASE_URL is required")
    provider_blocks = settings.providers.model_dump()
    for name in provider_blocks:
        value = store.get(f"providers__{name}__api_key")
        provider_blocks[name]["api_key"] = value
    settings = settings.model_copy(
        update={"providers": type(settings.providers).model_validate(provider_blocks)}
    )
    if not settings.providers.enabled():
        raise ValueError("Configure at least one provider API key in the secret store")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = None
        if key_repository is None:
            engine = create_async_engine(database_url.get_secret_value(), pool_pre_ping=True)
            app.state.key_repository = PostgresKeyRepository(
                async_sessionmaker(engine, expire_on_commit=False)
            )
        else:
            app.state.key_repository = key_repository
        try:
            async with provider_pools(settings) as registry:
                app.state.providers = registry
                log.info(
                    "gateway_started", version=__version__, providers=sorted(registry.adapters)
                )
                yield
        finally:
            if engine is not None:
                await engine.dispose()
        log.info("gateway_stopped")

    app = FastAPI(title="LLM Gateway", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.pepper = pepper.get_secret_value().encode()
    app.state.key_cache = key_cache or VerifiedKeyCache(
        settings.key_cache_ttl_s, settings.key_cache_max_size
    )
    app.include_router(health.router)
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])
    for module in (chat, embeddings):
        v1.include_router(module.router)
    app.include_router(v1)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_middleware(RequestContextMiddleware)
    return app
