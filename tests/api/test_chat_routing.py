import json

import httpx
import respx

from llm_gateway.config import ProvidersSettings, Settings
from llm_gateway.main import create_app
from llm_gateway.providers.registry import ADAPTER_TYPES
from tests.fixtures import COMPLETION


async def test_all_providers_are_available_in_one_app(upstream: respx.MockRouter) -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]  # ignore local developer .env
        providers=ProvidersSettings.model_validate(
            {
                name: {"api_key": f"fake-{name}", "base_url": f"https://{name}.test/v1"}
                for name in ADAPTER_TYPES
            }
        ),
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client,
    ):
        for name in ADAPTER_TYPES:
            route = upstream.post(f"https://{name}.test/v1/chat/completions").respond(
                200, json=COMPLETION
            )

            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": f"{name}/vendor/model",
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )

            assert response.status_code == 200
            assert response.json()["model"].startswith(f"{name}/")
            assert route.calls.last.request.headers["authorization"] == f"Bearer fake-{name}"
            assert json.loads(route.calls.last.request.content)["model"] == "vendor/model"
