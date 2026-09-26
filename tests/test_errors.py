import httpx


async def test_unknown_route_uses_the_openai_error_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"
    assert "x-request-id" in response.headers
