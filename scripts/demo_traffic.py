"""Tiny, synthetic gateway requests; never print content, responses or credentials."""

import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable

import httpx

MODELS = ("fast", "smart", "groq/openai/gpt-oss-20b", "openai/gpt-4.1-nano")
GATEWAY_URL = "http://127.0.0.1:18090/v1/chat/completions"


def traffic_payload(index: int) -> dict[str, object]:
    return {
        "model": MODELS[index % len(MODELS)],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize a synthetic support ticket for visitor@example.invalid."
                    if index % 4 == 0
                    else "Say hello to this synthetic demo."
                ),
            }
        ],
        "max_completion_tokens": 32,
        "stream": index % 5 == 0,
    }


async def send_traffic(client: httpx.AsyncClient, key: str, index: int) -> int:
    async with client.stream(
        "POST",
        GATEWAY_URL,
        json=traffic_payload(index),
        headers={"Authorization": f"Bearer {key}", "x-lgw-cache": "disabled"},
    ) as response:
        # Drain streaming/nonstreaming alike so final usage is recorded, without retaining text.
        async for _ in response.aiter_bytes():
            pass
        return response.status_code


async def run_traffic(
    client: httpx.AsyncClient,
    key: str,
    window_s: int,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> None:
    """One boot's traffic ends permanently, including when requests fail or run slowly."""
    if window_s <= 0:
        raise ValueError("DEMO_TRAFFIC_WINDOW_S must be a positive integer.")
    deadline = clock() + window_s
    index = 0
    while clock() < deadline:
        try:
            # A continuously streaming response must not outlive the boot window either.
            async with asyncio.timeout(deadline - clock()):
                status = await send_traffic(client, key, index)
            print(f"Synthetic demo traffic: status={status}.", flush=True)
        except (httpx.HTTPError, TimeoutError):
            print("Synthetic demo traffic: gateway unavailable.", flush=True)
        index += 1
        remaining = deadline - clock()
        if remaining <= 0:
            break
        await sleep(min(remaining, 0.2 if index < 3 else jitter(50, 70)))
    print("Synthetic demo traffic: window complete; stopping.", flush=True)


async def main() -> None:
    key = os.environ.get("DEMO_TENANT_KEY")
    if not key:
        raise SystemExit("Demo traffic needs its server-only tenant-key environment variable.")
    try:
        window_s = int(os.environ.get("DEMO_TRAFFIC_WINDOW_S", "600"))
        if window_s <= 0:
            raise ValueError
    except ValueError:
        raise SystemExit("DEMO_TRAFFIC_WINDOW_S must be a positive integer.") from None
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        await run_traffic(client, key, window_s)


if __name__ == "__main__":
    asyncio.run(main())
