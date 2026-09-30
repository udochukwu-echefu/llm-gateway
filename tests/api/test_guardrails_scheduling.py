import asyncio
import threading

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
    release = threading.Event()
    scan_finished = threading.Event()
    text = "1 " * ((2 * 1024 * 1024 - 256) // 2)
    get_app_state(resilient.app).settings.max_request_bytes = 2 * 1024 * 1024
    resilient.router.post("https://groq.test/v1/chat/completions").respond(200, json=COMPLETION)

    def observed_scan(value: str) -> list[Finding]:
        if value == text:
            loop.call_soon_threadsafe(started.set)
            if not release.wait(10):
                raise RuntimeError("health request did not release the test scan")
        findings = scan(value)
        if value == text:
            scan_finished.set()
        return findings

    monkeypatch.setattr("llm_gateway.guardrails.session.scan", observed_scan)
    request = asyncio.create_task(resilient.client.post("/v1/chat/completions", json=prompt(text)))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        async with asyncio.timeout(5):
            health = await resilient.client.get("/healthz")

        assert health.status_code == 200
        assert not scan_finished.is_set()
        release.set()
        assert (await request).status_code == 200
        assert scan_finished.is_set()
    finally:
        release.set()
        await request
