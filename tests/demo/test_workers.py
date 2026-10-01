import json
from typing import cast

import httpx
import respx
from respx.models import Call

from scripts.demo_traffic import GATEWAY_URL, MODELS, send_traffic, traffic_payload


def test_traffic_mix_has_aliases_models_streams_and_synthetic_email() -> None:
    payloads = [traffic_payload(index) for index in range(20)]
    assert {payload["model"] for payload in payloads} == set(MODELS)
    assert any("/" not in str(payload["model"]) for payload in payloads)
    assert {payload["stream"] for payload in payloads} == {True, False}
    assert sum("@example.invalid" in json.dumps(payload) for payload in payloads) == 5


async def test_traffic_drains_response_without_logging_content(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(GATEWAY_URL).mock(
        return_value=httpx.Response(200, content=b"synthetic-body")
    )
    async with httpx.AsyncClient() as client:
        assert await send_traffic(client, "synthetic-tenant-placeholder", 0) == 200
    assert route.called
    request = cast(Call, route.calls[0]).request
    assert json.loads(request.content)["stream"] is True
    assert request.headers["Authorization"] == "Bearer synthetic-tenant-placeholder"
