"""Tiny, synthetic gateway requests; never print content, responses or credentials."""

import asyncio
import os
import random

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


async def main() -> None:
    key = os.environ.get("DEMO_TENANT_KEY")
    if not key:
        raise SystemExit("Demo traffic needs its server-only tenant-key environment variable.")
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        index = 0
        while True:
            try:
                status = await send_traffic(client, key, index)
                print(f"Synthetic demo traffic: status={status}.")
            except httpx.HTTPError:
                print("Synthetic demo traffic: gateway unavailable.")
            index += 1
            # Three startup requests, then only internal traffic while the appliance is awake.
            await asyncio.sleep(0.2 if index < 3 else random.uniform(50, 70))  # noqa: S311 -- scheduling jitter, not a secret


if __name__ == "__main__":
    asyncio.run(main())
