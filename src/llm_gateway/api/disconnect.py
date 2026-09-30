"""Cancel pre-response provider work when the HTTP client has gone away."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import Request


async def until_disconnected[T](request: Request, call: Callable[[], Awaitable[T]]) -> T:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("HTTP execution requires an asyncio task")
    watcher = asyncio.create_task(_watch_disconnect(request, task))
    try:
        return await call()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


async def _watch_disconnect(request: Request, task: asyncio.Task[object]) -> None:
    # The endpoint has already read the complete request body. Stop this reader
    # before returning a StreamingResponse, which owns subsequent disconnect reads.
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            task.cancel()
            return
        await asyncio.sleep(0)
