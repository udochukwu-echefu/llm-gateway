"""Access timings use the identical observation as the histogram, without rounding."""

import pytest
import structlog
from structlog.testing import capture_logs

from tests.api.conftest import ResilientApp
from tests.fixtures import CHAT_REQUEST, COMPLETION, STREAM, USAGE_CHUNK, sse


@pytest.mark.parametrize("streaming", [False, True])
async def test_exact_overhead_and_key_cache_hit_miss_are_logged(
    resilient: ResilientApp, streaming: bool
) -> None:
    route = resilient.router.post("https://groq.test/v1/chat/completions")
    if streaming:
        route.respond(
            200,
            content=b"".join(sse(*STREAM, USAGE_CHUNK, "[DONE]")),
            headers={"content-type": "text/event-stream"},
        )
    else:
        route.respond(200, json=COMPLETION)

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        for _ in range(2):
            response = await resilient.client.post(
                "/v1/chat/completions", json={**CHAT_REQUEST, "stream": streaming}
            )
            assert response.status_code == 200
    records = [row for row in logs if row["event"] == "request"]

    assert [row["key_cache"] for row in records] == ["miss", "hit"]
    assert all(isinstance(row["overhead_ms"], float) and row["overhead_ms"] >= 0 for row in records)
    telemetry = resilient.app.state.gateway.telemetry
    observed = telemetry.metrics.registry.get_sample_value(
        "lgw_gateway_overhead_seconds_sum", {"route": "/v1/chat/completions"}
    )
    assert observed == pytest.approx(sum(row["overhead_ms"] / 1000 for row in records), abs=1e-12)
