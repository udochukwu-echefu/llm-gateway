"""Redis failures and corrupt entries are misses, never customer-facing errors."""

import asyncio
import time
from collections.abc import Callable

import structlog
from redis.asyncio import Redis

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.observability.metrics import Metrics

log = structlog.get_logger("llm_gateway.cache")


class ResponseCache:
    def __init__(
        self,
        client: Redis,
        cipher: CacheCipher,
        *,
        ttl: int = 3600,
        max_bytes: int = 1024 * 1024,
        timeout: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        metrics: Metrics | None = None,
    ) -> None:
        self.client, self.cipher = client, cipher
        self.ttl, self.max_bytes, self.timeout = ttl, max_bytes, timeout
        self.clock, self.metrics = clock, metrics
        self._last_error = 0.0
        self._flights: dict[str, asyncio.Future[bytes | None]] = {}

    async def lookup(self, key: str) -> tuple[bytes | None, bool]:
        try:
            async with asyncio.timeout(self.timeout):
                raw = await self.client.get(key)
            if raw is None:
                return None, True
            plain = self.cipher.open(key, raw)
            if plain is None:
                log.warning("cache_decryption_failed")
            return plain, True
        except Exception as exc:
            self._error(exc)
            return None, False

    async def store(self, key: str, data: bytes) -> None:
        if len(data) > self.max_bytes:
            return
        try:
            async with asyncio.timeout(self.timeout):
                await self.client.set(key, self.cipher.seal(key, data), ex=self.ttl)
        except Exception as exc:
            self._error(exc)

    def enter(self, key: str) -> tuple[asyncio.Future[bytes | None], bool]:
        flight = self._flights.get(key)
        if flight is not None:
            return flight, False
        flight = asyncio.get_running_loop().create_future()
        self._flights[key] = flight
        return flight, True

    def leave(self, key: str, flight: asyncio.Future[bytes | None], data: bytes | None) -> None:
        if self._flights.get(key) is flight:
            self._flights.pop(key)
        if not flight.done():
            flight.set_result(data)

    def _error(self, exc: Exception) -> None:
        if self.metrics is not None:
            self.metrics.redis_errors.labels("cache").inc()
        now = self.clock()
        if now - self._last_error >= 1 or self._last_error == 0:
            log.error("cache_dependency_unavailable", error_type=type(exc).__name__)
            self._last_error = now
