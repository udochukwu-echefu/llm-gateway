"""Canonical fingerprints and encryption-key validation."""

import base64
import json
import uuid

import pytest
from pydantic import SecretStr, ValidationError

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.key import cache_key
from llm_gateway.config import CacheSettings, Settings
from llm_gateway.schemas.chat import ChatCompletionRequest
from tests.conftest import MemoryKeyRepository


def test_key_stability_exclusions_provider_options_and_version() -> None:
    team = uuid.uuid4()
    request = ChatCompletionRequest.model_validate(
        {
            "model": "fast",
            "messages": [{"role": "user", "content": "PRIVATE_MARKER"}],
            "temperature": 1,
            "user": "one",
            "provider_options": {"groq": {"flag": 1}},
        }
    )
    reordered = ChatCompletionRequest.model_validate_json(
        json.dumps(
            {
                "provider_options": {"groq": {"flag": 1}},
                "user": "two",
                "temperature": 1.0,
                "messages": [{"content": "PRIVATE_MARKER", "role": "user"}],
                "model": "fast",
            },
            indent=2,
        )
    )
    first = cache_key(team, "chat", "groq/model", request, "v1")

    assert first == cache_key(team, "chat", "groq/model", reordered, "v1")
    assert first != cache_key(team, "chat", "groq/model", request, "v2")
    assert first != cache_key(team, "chat", "deepseek/model", request, "v1")
    assert first != cache_key(uuid.uuid4(), "chat", "groq/model", request, "v1")
    changed = request.model_copy(update={"provider_options": {"groq": {"flag": 2}}})
    assert first != cache_key(team, "chat", "groq/model", changed, "v1")
    assert "PRIVATE_MARKER" not in first


def test_missing_or_invalid_key_fails_startup(
    settings: Settings, memory_repository: MemoryKeyRepository
) -> None:
    from llm_gateway.main import create_app
    from tests.conftest import OfflineLimitService

    enabled = settings.model_copy(
        update={"cache": settings.cache.model_copy(update={"enabled": True})}
    )

    class Missing:
        def get(self, name: str) -> SecretStr | None:
            return None if name == "cache_encryption_key" else SecretStr("x" * 40)

    with pytest.raises(ValueError, match="CACHE_ENCRYPTION_KEY"):
        create_app(
            enabled,
            key_repository=memory_repository,
            limit_service=OfflineLimitService(),
            secret_store=Missing(),
        )
    with pytest.raises(ValueError, match="base64"):
        CacheCipher(SecretStr("not base64"))


def test_unknown_key_id_is_miss() -> None:
    cipher = CacheCipher(SecretStr(base64.b64encode(b"c" * 32).decode()))
    assert cipher.open("lgw:cache:key", b"0" * 50) is None


def test_ttl_is_capped_at_seven_days() -> None:
    assert CacheSettings().ttl_s == 3600
    with pytest.raises(ValidationError):
        CacheSettings(ttl_s=7 * 24 * 3600 + 1)
