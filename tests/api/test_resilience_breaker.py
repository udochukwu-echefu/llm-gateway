import pytest

from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST

pytestmark = pytest.mark.respx(assert_all_called=False)


@pytest.mark.parametrize("status", [400, 401, 403, 408, 422])
async def test_client_errors_do_not_trip_breaker(resilient: ResilientApp, status: int) -> None:
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(status)
    for _ in range(12):
        await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    assert route.call_count == 12
    assert resilient.service.breakers["groq"].state == "closed"


@pytest.mark.parametrize("status", [429, 500, 503, 529])
async def test_breaker_opens_at_threshold_and_fails_without_network(
    resilient: ResilientApp, status: int
) -> None:
    resilient.service.settings.max_retries = 0
    route = resilient.router.post("https://groq.test/v1/chat/completions").respond(status)
    for _ in range(10):
        await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    response = await resilient.client.post("/v1/chat/completions", json=CHAT_REQUEST)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert route.call_count == 10
