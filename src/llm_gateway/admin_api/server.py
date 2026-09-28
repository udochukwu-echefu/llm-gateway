"""Lifespan-owned private uvicorn listener."""

import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from llm_gateway.config import AdminApiSettings


class _ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self.ready = asyncio.Event()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        self.ready.set()


@asynccontextmanager
async def admin_server(settings: AdminApiSettings, app: FastAPI) -> AsyncGenerator[None]:
    if not settings.enabled:
        yield
        return
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
        lifespan="off",
    )
    server = _ReadyServer(config)
    task = asyncio.create_task(server.serve())
    ready_task = asyncio.create_task(server.ready.wait())
    try:
        await asyncio.wait((task, ready_task), return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            task.result()
        if not server.started:
            raise RuntimeError("Admin listener failed to start")
        yield
    finally:
        ready_task.cancel()
        server.should_exit = True
        await task
