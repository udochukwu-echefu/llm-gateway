from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from llm_gateway import __version__
from llm_gateway.api import chat, embeddings, health
from llm_gateway.config import Settings
from llm_gateway.errors import GatewayError, gateway_error_handler, http_exception_handler
from llm_gateway.logging import configure_logging
from llm_gateway.middleware import RequestContextMiddleware
from llm_gateway.upstream import UpstreamClient

log = structlog.get_logger("llm_gateway")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Run with `uvicorn llm_gateway.main:create_app --factory`."""
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]  # values come from env
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # One pooled client for the life of the process: reusing connections avoids a TCP and
        # TLS handshake on every request.
        async with httpx.AsyncClient(
            base_url=settings.upstream_base_url,
            headers={"authorization": f"Bearer {settings.upstream_api_key.get_secret_value()}"},
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_s,
                read=settings.read_timeout_s,
                write=settings.write_timeout_s,
                pool=settings.pool_timeout_s,
            ),
            limits=httpx.Limits(
                max_connections=settings.max_connections,
                max_keepalive_connections=settings.max_keepalive_connections,
            ),
        ) as http:
            app.state.upstream = UpstreamClient(http)
            log.info("gateway_started", version=__version__, upstream=settings.upstream_base_url)
            yield
        log.info("gateway_stopped")

    app = FastAPI(title="LLM Gateway", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    for module in (health, chat, embeddings):
        app.include_router(module.router)
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_middleware(RequestContextMiddleware)
    return app
