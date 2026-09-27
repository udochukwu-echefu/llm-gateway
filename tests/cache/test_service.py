"""Redis integration: TTL, encryption and associated-data binding."""

import base64
import uuid

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.service import ResponseCache

pytestmark = pytest.mark.redis


async def test_ciphertext_in_redis_expires_and_cannot_move_between_teams(
    test_redis: Redis,
) -> None:
    cipher = CacheCipher(SecretStr(base64.b64encode(b"r" * 32).decode()))
    cache = ResponseCache(test_redis, cipher, ttl=3)
    team_a, team_b = uuid.uuid4(), uuid.uuid4()
    first, second = f"lgw:cache:{team_a}:hash", f"lgw:cache:{team_b}:hash"
    try:
        await cache.store(first, b"PRIVATE_ANSWER")
        raw = await test_redis.get(first)
        assert raw is not None
        assert b"PRIVATE_ANSWER" not in raw
        assert 0 < await test_redis.ttl(first) <= 3
        await test_redis.set(second, raw, ex=3)

        assert await cache.lookup(first) == (b"PRIVATE_ANSWER", True)
        assert await cache.lookup(second) == (None, True)
    finally:
        await test_redis.delete(first, second)
