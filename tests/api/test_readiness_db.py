import httpx
import pytest
from sqlalchemy.engine import make_url

from llm_gateway.config import Settings
from tests.tenants.support import database_app

pytestmark = pytest.mark.db


async def test_readyz_returns_200_with_postgres_up(
    migrated_database: str, settings: Settings
) -> None:
    app = database_app(settings, migrated_database)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "redis": "ok"}


async def test_readyz_returns_503_when_postgres_unreachable(
    migrated_database: str, settings: Settings
) -> None:
    unavailable_url = make_url(migrated_database).set(port=1).render_as_string(hide_password=False)
    app = database_app(settings, unavailable_url)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
