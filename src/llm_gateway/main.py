from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import APIRouter, Depends, FastAPI
from opentelemetry import trace
from opentelemetry.trace import TracerProvider
from prometheus_client import CollectorRegistry
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_gateway import __version__
from llm_gateway.admin.api.app import create_admin_app
from llm_gateway.admin.api.auth import AdminContext
from llm_gateway.admin.api.server import admin_server
from llm_gateway.api import chat, embeddings, health, models
from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.service import ResponseCache
from llm_gateway.catalog import Catalog, load_catalog
from llm_gateway.config import Settings
from llm_gateway.errors import GatewayError, gateway_error_handler, http_exception_handler
from llm_gateway.gateway_state import GatewayState
from llm_gateway.limits.reconcile import BudgetReconciler
from llm_gateway.limits.service import LimitService
from llm_gateway.logging import configure_logging
from llm_gateway.middleware import RequestContextMiddleware
from llm_gateway.observability.metrics import Metrics
from llm_gateway.observability.middleware import ObservabilityMiddleware
from llm_gateway.observability.server import metrics_server
from llm_gateway.observability.tracing import Telemetry, make_provider
from llm_gateway.providers.pools import provider_pools
from llm_gateway.resilience.service import ResilienceService
from llm_gateway.secrets import EnvSecretStore, FileSecretStore, SecretStore
from llm_gateway.storage_connections import database_engine, redis_connection
from llm_gateway.tenants.auth import authenticate
from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.repository import KeyRepository, PostgresKeyRepository
from llm_gateway.usage.middleware import UsageMiddleware
from llm_gateway.usage.repository import PostgresUsageRepository
from llm_gateway.usage.writer import Sink, UsageWriter

log = structlog.get_logger("llm_gateway")


def create_app(
    settings: Settings | None = None,
    key_repository: KeyRepository | None = None,
    secret_store: SecretStore | None = None,
    key_cache: VerifiedKeyCache | None = None,
    catalog: Catalog | None = None,
    usage_sink: Sink | None = None,
    limit_service: LimitService | None = None,
    metrics_registry: CollectorRegistry | None = None,
    tracer_provider: TracerProvider | None = None,
) -> FastAPI:
    """Build the application. Run with `uvicorn llm_gateway.main:create_app --factory`."""
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]  # values come from env
    configure_logging(settings.log_level, settings.log_format)
    fallbacks: dict[str, SecretStr | None] = {
        "api_key_pepper": settings.api_key_pepper,
        "database_url": settings.database_url,
        "redis_url": settings.redis_url,
        "cache_encryption_key": settings.cache_encryption_key,
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
    redis_url = store.get("redis_url")
    cache_secret = store.get("cache_encryption_key") if settings.cache.enabled else None
    if settings.cache.enabled and cache_secret is None:
        raise ValueError("GATEWAY_CACHE_ENCRYPTION_KEY is required when caching is enabled")
    cipher = CacheCipher(cache_secret) if cache_secret is not None else None
    if pepper is None or len(pepper.get_secret_value().encode()) < 32:
        raise ValueError("GATEWAY_API_KEY_PEPPER is required and must be at least 32 bytes")
    if database_url is None or not database_url.get_secret_value():
        raise ValueError("GATEWAY_DATABASE_URL is required")
    if limit_service is None and (redis_url is None or not redis_url.get_secret_value()):
        raise ValueError("GATEWAY_REDIS_URL is required")
    provider_blocks = settings.providers.model_dump()
    for name in provider_blocks:
        value = store.get(f"providers__{name}__api_key")
        provider_blocks[name]["api_key"] = value
    settings = settings.model_copy(
        update={"providers": type(settings.providers).model_validate(provider_blocks)}
    )
    if not settings.providers.enabled():
        raise ValueError("Configure at least one provider API key in the secret store")
    settings.validate_provider_timeouts()
    settings.validate_demo_providers()
    catalog = catalog if catalog is not None else load_catalog()

    metrics = Metrics(metrics_registry if metrics_registry is not None else CollectorRegistry())
    telemetry = Telemetry(metrics, trace.NoOpTracer(), settings.tracing.propagate_to_providers)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = None
        if key_repository is None:
            engine = database_engine(database_url.get_secret_value(), demo=settings.demo_deployment)
            repository: KeyRepository = PostgresKeyRepository(
                async_sessionmaker(engine, expire_on_commit=False)
            )
        else:
            repository = key_repository
        usage_repository = (
            PostgresUsageRepository(async_sessionmaker(engine, expire_on_commit=False))
            if engine is not None
            else None
        )
        redis_client: Redis | None = None
        limits = limit_service
        if limits is None:
            if redis_url is None:
                raise RuntimeError("Redis URL was not resolved")
            redis_client = redis_connection(
                redis_url.get_secret_value(),
                settings.limits.redis_timeout_s,
                demo=settings.demo_deployment,
            )
            limits = LimitService(
                redis_client,
                fail_mode=settings.limits.fail_mode,
                lease_ttl=settings.limits.lease_ttl_s,
                ip_limit=settings.limits.ip_failures_per_minute,
                rpm_burst=settings.limits.rpm_burst,
                rebuild_timeout=settings.limits.budget_rebuild_timeout_s,
                spend_total=usage_repository.month_spend if usage_repository is not None else None,
            )
        sink = usage_sink
        if sink is None:
            if engine is None:

                async def discard_test_usage(records: object) -> None:
                    pass

                sink = discard_test_usage
            else:
                if usage_repository is None:
                    raise RuntimeError("Usage repository missing")
                sink = usage_repository.insert
        writer = UsageWriter(
            sink,
            max_size=settings.usage_queue_size,
            batch_size=settings.usage_batch_size,
            interval=settings.usage_flush_interval_s,
            metrics=metrics,
        )
        reconciler = (
            BudgetReconciler(
                limits,
                usage_repository,
                writer,
                interval=settings.limits.budget_reconcile_interval_s,
            )
            if redis_client is not None and usage_repository is not None
            else None
        )
        limits.metrics = metrics
        try:
            async with AsyncExitStack() as stack:
                owned_provider = (
                    make_provider(settings.tracing) if tracer_provider is None else None
                )
                if owned_provider is not None:
                    stack.callback(owned_provider.shutdown)
                provider = tracer_provider or owned_provider
                telemetry.tracer = (
                    provider.get_tracer("llm-gateway") if provider else trace.NoOpTracer()
                )
                await stack.enter_async_context(metrics_server(settings.metrics, metrics.registry))
                if settings.admin_api.enabled:
                    if engine is None or redis_client is None:
                        raise ValueError("Admin API requires owned Postgres and Redis connections")
                    admin_app = create_admin_app(
                        AdminContext(
                            async_sessionmaker(engine, expire_on_commit=False),
                            pepper.get_secret_value().encode(),
                            limits,
                            redis_client,
                            settings.trusted_proxy_hops,
                            settings,
                            lambda: (
                                {
                                    name: breaker.state
                                    for name, breaker in (
                                        app.state.gateway.resilience.breakers.items()
                                    )
                                }
                                if hasattr(app.state, "gateway")
                                else {}
                            ),
                        )
                    )
                    await stack.enter_async_context(admin_server(settings.admin_api, admin_app))
                registry = await stack.enter_async_context(provider_pools(settings))
                app.state.gateway = GatewayState(
                    settings=settings,
                    providers=registry,
                    key_repository=repository,
                    key_cache=key_cache
                    if key_cache is not None
                    else VerifiedKeyCache(settings.key_cache_ttl_s, settings.key_cache_max_size),
                    pepper=pepper.get_secret_value().encode(),
                    catalog=catalog,
                    usage_writer=writer,
                    resilience=ResilienceService(
                        registry, catalog, settings.resilience, metrics=metrics
                    ),
                    limits=limits,
                    telemetry=telemetry,
                    response_cache=(
                        ResponseCache(
                            limits.client,
                            cipher,
                            ttl=settings.cache.ttl_s,
                            max_bytes=settings.cache.max_entry_bytes,
                            timeout=settings.limits.redis_timeout_s,
                            metrics=metrics,
                        )
                        if cipher is not None
                        else None
                    ),
                )
                writer.start()
                if reconciler is not None:
                    reconciler.start()
                log.info(
                    "gateway_started", version=__version__, providers=sorted(registry.adapters)
                )
                try:
                    yield
                finally:
                    try:
                        if reconciler is not None:
                            await reconciler.stop()
                    finally:
                        await writer.stop(settings.usage_shutdown_timeout_s)
        finally:
            if redis_client is not None:
                await redis_client.aclose()
            if engine is not None:
                await engine.dispose()
        log.info("gateway_stopped")

    app = FastAPI(title="LLM Gateway", version=__version__, lifespan=lifespan)
    app.include_router(health.router)
    v1 = APIRouter(prefix="/v1", dependencies=[Depends(authenticate)])
    for module in (chat, embeddings, models):
        v1.include_router(module.router)
    app.include_router(v1)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_middleware(UsageMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ObservabilityMiddleware, telemetry=telemetry)
    return app
