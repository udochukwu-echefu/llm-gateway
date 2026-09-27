import httpx
import pytest

from tests.live.models import LiveProvider

pytestmark = pytest.mark.live


async def test_live_reviewed_alias_resolves_end_to_end(
    live_provider: LiveProvider, live_client: httpx.AsyncClient
) -> None:
    if live_provider.name == "openai":
        pytest.skip("Reviewed aliases currently target Groq, DeepSeek and Gemini")
    alias = "embed" if live_provider.name == "gemini" else "fast"
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
