"""HTTP resilience fixtures use distinct provider hosts and deterministic policy time."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field, replace

import httpx
import pytest
import respx
from fastapi import FastAPI

from llm_gateway.catalog import Catalog
from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.gateway_state import get_app_state
from llm_gateway.main import create_app
from llm_gateway.resilience.service import ResilienceService
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
        # Earn two retries from prior first attempts; production starts with no credit.
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
