"""A private scrape socket owned by the application lifespan."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from prometheus_client import CollectorRegistry, start_http_server

from llm_gateway.observability.configuration import MetricsSettings


@asynccontextmanager
async def metrics_server(
    settings: MetricsSettings, registry: CollectorRegistry
) -> AsyncGenerator[None]:
    if not settings.enabled:
        yield
        return
    server, thread = start_http_server(settings.port, addr=settings.host, registry=registry)
    try:
        yield
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        await asyncio.to_thread(thread.join)
