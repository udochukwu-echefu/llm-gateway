"""A refused local Groq connection must recover through the real DeepSeek API."""

import os
import socket
import uuid

import httpx
import pytest
from pydantic import SecretStr

from llm_gateway.catalog import load_catalog
from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.main import create_app
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import KeyRecord
from tests.conftest import MemoryKeyRepository, OfflineLimitService

pytestmark = pytest.mark.live


async def test_closed_groq_port_falls_back_to_live_deepseek() -> None:
    if not os.environ.get("GATEWAY_PROVIDERS__DEEPSEEK__API_KEY"):
        pytest.skip("No environment key configured for deepseek")
    settings = Settings()  # pyright: ignore[reportCallIssue]  # live settings come from environment
    pepper = b"fake-live-fallback-pepper-32-bytes-minimum"
    issued = issue_key(pepper)
    repo = MemoryKeyRepository()
    repo.records[issued.key_id] = KeyRecord(
        issued.key_id, issued.secret_hash, uuid.uuid4(), uuid.uuid4()
    )
    catalog = load_catalog()
    primary = catalog.find("groq", "openai/gpt-oss-20b", "chat")
    assert primary is not None
    primary.fallbacks = ["deepseek/deepseek-flash"]
    catalog = type(catalog).model_validate(catalog.model_dump())

    class LiveStore:
        def get(self, name: str) -> SecretStr | None:
            return {
                "api_key_pepper": SecretStr(pepper.decode()),
                "database_url": SecretStr("postgresql+asyncpg://fake:fake@127.0.0.1:1/fake"),
                "providers__groq__api_key": SecretStr("fake-local-only"),
                "providers__deepseek__api_key": settings.providers.deepseek.api_key,
            }.get(name)

    # Bound but not listening: reserve a port that will refuse connections throughout the test.
    with socket.socket() as closed_port:
        closed_port.bind(("127.0.0.1", 0))
        providers = ProvidersSettings.model_validate(
            {
                "groq": {
                    "api_key": "fake-local-only",
                    "base_url": f"http://127.0.0.1:{closed_port.getsockname()[1]}/v1",
                },
                "deepseek": settings.providers.deepseek,
            }
        )
        app = create_app(
            settings.model_copy(update={"providers": providers}),
            key_repository=repo,
            secret_store=LiveStore(),
            catalog=catalog,
            limit_service=OfflineLimitService(),
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gateway.test",
                headers={"authorization": f"Bearer {issued.full_key}"},
            ) as client,
        ):
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "groq/openai/gpt-oss-20b",
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 32,
                },
            )
    assert response.status_code == 200
    assert response.json()["model"].startswith("deepseek/")
    assert response.headers["x-lgw-fallback-from"] == "groq/openai/gpt-oss-20b"
    assert response.headers["x-lgw-attempts"] == "2"
