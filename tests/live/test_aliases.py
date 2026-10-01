import httpx
import pytest

from llm_gateway.catalog import load_catalog
from tests.live.models import PROVIDERS, LiveProvider

pytestmark = pytest.mark.live


ALIAS_CASES = [
    pytest.param(provider, alias, id=target.model)
    for alias, definition in load_catalog().aliases.items()
    for target in definition.targets
    for provider in PROVIDERS
    if target.model
    in {
        f"{provider.name}/{provider.chat_model}",
        f"{provider.name}/{provider.embedding_model}",
    }
]


@pytest.mark.parametrize(("live_provider", "alias"), ALIAS_CASES, indirect=["live_provider"])
async def test_live_reviewed_alias_resolves_end_to_end(
    live_provider: LiveProvider, live_client: httpx.AsyncClient, alias: str
) -> None:
    if alias == "embed":
        response = await live_client.post("/v1/embeddings", json={"model": alias, "input": "hello"})
    else:
        response = await live_client.post(
            "/v1/chat/completions",
            json={"model": alias, "messages": [{"role": "user", "content": "Reply only with OK."}]},
        )

    assert response.status_code == 200
    assert response.headers["x-lgw-alias"] == alias
    assert response.json()["model"].startswith(f"{live_provider.name}/")
