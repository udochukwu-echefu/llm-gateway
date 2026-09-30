"""Exercise the opt-in live history flow offline so it cannot silently drop reasoning."""

import json
from typing import cast

import httpx
import pytest
import respx

from tests.live.models import NVIDIA_KIMI
from tests.live.test_providers import (
    test_live_kimi_multi_turn_replays_complete_assistant_message as run_multi_turn,
)
from tests.providers.conftest import HostedGateway
from tests.providers.fixtures import hosted_completion

pytestmark = pytest.mark.parametrize("provider_name", ["nvidia"])


async def test_live_kimi_history_flow_replays_reasoning_in_second_upstream_request(
    hosted_gateway: HostedGateway,
    upstream: respx.MockRouter,
) -> None:
    completion = hosted_completion(NVIDIA_KIMI.chat_model)
    route = upstream.post("/chat/completions").respond(200, json=completion)

    await run_multi_turn(NVIDIA_KIMI, hosted_gateway.client, hosted_gateway.records)

    assert route.call_count == 2
    first = json.loads(cast(httpx.Request, route.calls[0][0]).content)
    second = json.loads(route.calls.last.request.content)
    assert second["messages"][0] == first["messages"][0]
    assert second["messages"][1] == completion["choices"][0]["message"]
    assert second["messages"][1]["reasoning_content"] == "Analysis"
    assert second["model"] == "moonshotai/kimi-k3"
