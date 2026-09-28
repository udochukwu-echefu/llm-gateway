"""HTTP resilience fixtures use distinct provider hosts and deterministic policy time."""

import base64
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field, replace
from typing import cast

import httpx
import pytest
import respx
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis

from llm_gateway.cache.crypto import CacheCipher
from llm_gateway.cache.service import ResponseCache
from llm_gateway.catalog import Catalog
from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.policy import GuardrailPolicy, Region
from llm_gateway.main import create_app
from llm_gateway.resilience.service import ResilienceService
from llm_gateway.routing.policy import ModelPolicy
from llm_gateway.usage.record import UsageRecord
from tests.conftest import UPSTREAM_KEY, MemoryKeyRepository, OfflineLimitService


@dataclass
class FakeTime:
    now: float = 0.0
    delays: list[float] = field(default_factory=list[float])

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.now += delay


@dataclass
class ResilientApp:
    app: FastAPI
    client: httpx.AsyncClient
    service: ResilienceService
    records: list[UsageRecord]
    router: respx.MockRouter
    time: FakeTime

    def fallbacks(self, *targets: str) -> None:
        price = self.service.catalog.find("groq", "llama-3.3-70b-versatile", "chat")
        assert price is not None
        price.fallbacks = list(targets)


@dataclass
class MemoryRedis:
    values: dict[str, bytes] = field(default_factory=lambda: dict[str, bytes]())
    available: bool = True

    async def get(self, key: str) -> bytes | None:
        if not self.available:
            raise ConnectionError("offline")
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ex: int) -> bool:
        if not self.available:
            raise ConnectionError("offline")
        self.values[key] = value
        return True


@pytest.fixture
def cached(resilient: ResilientApp) -> tuple[ResilientApp, MemoryRedis]:
    redis = MemoryRedis()
    state = get_app_state(resilient.app)
    cipher = CacheCipher(SecretStr(base64.b64encode(b"c" * 32).decode()))
    service = ResponseCache(
        cast(Redis, redis), cipher, metrics=state.telemetry.metrics if state.telemetry else None
    )
    resilient.app.state.gateway = replace(state, response_cache=service)
    return resilient, redis


@pytest.fixture
async def resilient(
    settings: Settings,
    memory_repository: MemoryKeyRepository,
    test_catalog: Catalog,
    issued_test_key: str,
    respx_mock: respx.MockRouter,
) -> AsyncIterator[ResilientApp]:
    records: list[UsageRecord] = []

    async def sink(batch: Sequence[UsageRecord]) -> None:
        records.extend(batch)

    providers = ProvidersSettings.model_validate(
        {
            name: {
                "base_url": f"https://{name}.test/v1",
                "api_key": UPSTREAM_KEY,
            }
            for name in ("groq", "deepseek", "openai", "gemini")
        }
    )
    app = create_app(
        settings.model_copy(update={"providers": providers, "usage_batch_size": 1}),
        key_repository=memory_repository,
        catalog=test_catalog,
        usage_sink=sink,
        limit_service=OfflineLimitService(),
    )
    settings.resilience.retry_budget_min_per_window = 0
    fake = FakeTime()
    async with app.router.lifespan_context(app):
        state = get_app_state(app)
        service = ResilienceService(
            state.providers,
            test_catalog,
            settings.resilience,
            clock=fake.clock,
            sleep=fake.sleep,
            random_source=lambda: 0.5,
        )
        # Exercise the proportional budget independently of the production floor.
        for budget in service.budgets.values():
            for _ in range(10):
                budget.first()
        app.state.gateway = replace(state, resilience=service)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client:
            yield ResilientApp(app, client, service, records, respx_mock, fake)


@pytest.fixture
def set_policy(memory_repository: MemoryKeyRepository):
    from llm_gateway.routing.policy import ModelPolicy

    def apply(org: tuple[str, ...] | None = None, team: tuple[str, ...] | None = None) -> None:
        record = next(iter(memory_repository.records.values()))
        memory_repository.records[record.key_id] = replace(record, policy=ModelPolicy(org, team))

    return apply


@pytest.fixture
async def aliased(resilient: ResilientApp) -> ResilientApp:
    from llm_gateway.routing.aliases import Alias

    resilient.service.catalog.aliases = {
        "fast": Alias.model_validate(
            {
                "targets": [
                    {"model": "groq/model", "weight": 90},
                    {"model": "deepseek/model", "weight": 10},
                ]
            }
        ),
        "private": Alias.model_validate({"targets": [{"model": "deepseek/model", "weight": 1}]}),
        "embed": Alias.model_validate({"targets": [{"model": "openai/embedding", "weight": 1}]}),
    }
    return resilient


@pytest.fixture
def set_guardrails(memory_repository: MemoryKeyRepository):
    def apply(policy: GuardrailPolicy) -> None:
        record = next(iter(memory_repository.records.values()))
        memory_repository.records[record.key_id] = replace(record, guardrails=policy)

    return apply


@pytest.fixture
def set_residency(memory_repository: MemoryKeyRepository, test_catalog: Catalog):
    # Synthetic regions test routing; they do not claim real provider locations.
    for entry in test_catalog.models:
        entry.region = "us" if entry.provider == "groq" else "cn"

    def apply(org: tuple[Region, ...] | None, team: tuple[Region, ...] | None = None) -> None:
        record = next(iter(memory_repository.records.values()))
        memory_repository.records[record.key_id] = replace(
            record, policy=ModelPolicy(organization_regions=org, team_regions=team)
        )

    return apply
