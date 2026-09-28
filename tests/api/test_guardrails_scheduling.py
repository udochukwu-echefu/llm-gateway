import asyncio
import time

import pytest

from llm_gateway.gateway_state import get_app_state
from llm_gateway.guardrails.detectors import Finding, scan
from tests.api.conftest import ResilientApp
from tests.fixtures import COMPLETION
from tests.guardrails.fixtures import prompt


async def test_health_stays_responsive_during_large_numeric_scan(
    resilient: ResilientApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    loop = asyncio.get_running_loop()
    began = 0.0
    scan_finished = 0.0
    text = "1 " * ((2 * 1024 * 1024 - 256) // 2)
    get_app_state(resilient.app).settings.max_request_bytes = 2 * 1024 * 1024
    resilient.router.post("https://groq.test/v1/chat/completions").respond(200, json=COMPLETION)

    def observed_scan(value: str) -> list[Finding]:
        nonlocal began, scan_finished
        if value == text:
            began = time.monotonic()
            loop.call_soon_threadsafe(started.set)
        findings = scan(value)
        if value == text:
            scan_finished = time.monotonic()
        return findings

    monkeypatch.setattr("llm_gateway.guardrails.session.scan", observed_scan)
    request = asyncio.create_task(resilient.client.post("/v1/chat/completions", json=prompt(text)))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        health = await resilient.client.get("/healthz")
        health_answered = time.monotonic()
        elapsed = health_answered - began

        assert health.status_code == 200
        assert (await request).status_code == 200
        assert health_answered < scan_finished
        assert elapsed < 2.0
    finally:
        await request
