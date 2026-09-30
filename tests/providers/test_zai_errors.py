"""Business errors must be classified before resilience decides whether to retry."""

from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from structlog.testing import capture_logs

from llm_gateway.config import Settings
from llm_gateway.main import create_app
from tests.conftest import MemoryKeyRepository, OfflineLimitService

pytestmark = pytest.mark.parametrize("provider_name", ["zai"])
ACCOUNT_CODES = (
    "1113",
    "1308",
    "1309",
    "1310",
    "1311",
    "1313",
    "1314",
    "1315",
    "1316",
    "1317",
    "1318",
    "1319",
    "1320",
    "1321",
)


@pytest.fixture
async def retrying_client(
    settings: Settings, memory_repository: MemoryKeyRepository, issued_test_key: str
) -> AsyncIterator[httpx.AsyncClient]:
    settings.resilience.max_retries = 2
    app = create_app(
        settings, key_repository=memory_repository, limit_service=OfflineLimitService()
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://gateway.test",
            headers={"authorization": f"Bearer {issued_test_key}"},
        ) as client,
    ):
        yield client


@pytest.mark.parametrize("business_code", ACCOUNT_CODES)
@pytest.mark.parametrize("stream", [False, True])
async def test_account_errors_are_sanitized_and_not_retried(
    retrying_client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    business_code: str,
    stream: bool,
) -> None:
    private_message = "Insufficient balance or no resource package. Please recharge."
    route = upstream.post("/chat/completions").respond(
        429,
        json={"error": {"code": business_code, "message": private_message}},
        headers={"retry-after": "0"},
    )

    with capture_logs() as logs:
        response = await retrying_client.post(
            "/v1/chat/completions",
            json={
                "model": "zai/glm-5.3-flash",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": stream,
            },
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_account_error"
    assert route.call_count == 1
    assert "retry-after" not in response.headers
    assert private_message not in response.text
    events = [event for event in logs if event["event"] == "upstream_account_error"]
    assert len(events) == 1
    assert events[0]["business_code"] == business_code
    assert events[0]["action"] == "check_provider_billing_quota_and_entitlements"
    assert private_message not in str(logs)


@pytest.mark.parametrize("business_code", ["1302", "1305", "unknown"])
async def test_rate_limits_keep_existing_retry_path(
    retrying_client: httpx.AsyncClient,
    upstream: respx.MockRouter,
    business_code: str,
) -> None:
    route = upstream.post("/chat/completions").respond(
        429,
        json={"error": {"code": business_code, "message": "Try later"}},
        headers={"retry-after": "0"},
    )

    response = await retrying_client.post(
        "/v1/chat/completions",
        json={"model": "zai/glm-5.3-flash", "messages": [{"role": "user", "content": "Hi"}]},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "upstream_rate_limited"
    assert route.call_count == 3
