import httpx

from tests.conftest import MemoryKeyRepository


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_503_when_database_unreachable(
    client: httpx.AsyncClient, memory_repository: MemoryKeyRepository
) -> None:
    memory_repository.available = False

    response = await client.get("/readyz")
    live = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert live.status_code == 200
