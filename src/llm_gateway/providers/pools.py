from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import httpx

from llm_gateway.providers.base import ProviderAdapter
from llm_gateway.providers.registry import ADAPTER_TYPES, ProviderRegistry

if TYPE_CHECKING:
    from llm_gateway.config import Settings


@asynccontextmanager
async def provider_pools(settings: Settings) -> AsyncGenerator[ProviderRegistry]:
    """Separate connection pools isolate providers, even during partial startup failure."""
    async with AsyncExitStack() as stack:
        adapters: list[ProviderAdapter] = []
        for name, block in settings.providers.enabled():
            if block.api_key is None:
                continue
            http = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=str(block.base_url).rstrip("/") + "/",
                    headers={"authorization": f"Bearer {block.api_key.get_secret_value()}"},
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
                )
            )
            adapters.append(ADAPTER_TYPES[name](http))
        yield ProviderRegistry(adapters)
