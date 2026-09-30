from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx

from llm_gateway.config import Settings
from llm_gateway.providers.base import ProviderAdapter
from llm_gateway.providers.defaults import DEFAULT_BASE_URLS
from llm_gateway.providers.registry import ADAPTER_TYPES, ProviderRegistry


@asynccontextmanager
async def provider_pools(settings: Settings) -> AsyncGenerator[ProviderRegistry]:
    """Separate connection pools isolate providers, even during partial startup failure."""
    async with AsyncExitStack() as stack:
        adapters: list[ProviderAdapter] = []
        for name, block in settings.providers.enabled():
            if block.api_key is None:
                continue
            timeouts = settings.provider_timeouts(name, block)
            http = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=str(block.base_url or DEFAULT_BASE_URLS[name]).rstrip("/") + "/",
                    headers={"authorization": f"Bearer {block.api_key.get_secret_value()}"},
                    timeout=httpx.Timeout(
                        connect=timeouts.connect,
                        read=timeouts.read,
                        write=timeouts.write,
                        pool=timeouts.pool,
                    ),
                    limits=httpx.Limits(
                        max_connections=settings.max_connections,
                        max_keepalive_connections=settings.max_keepalive_connections,
                    ),
                )
            )
            adapters.append(ADAPTER_TYPES[name](http))
        yield ProviderRegistry(adapters)
