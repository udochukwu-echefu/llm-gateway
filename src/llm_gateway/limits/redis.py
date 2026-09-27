"""Small Redis script runner; script reload is safe after Redis restarts or SCRIPT FLUSH."""

from collections.abc import Awaitable
from importlib.resources import files
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import NoScriptError


class Scripts:
    def __init__(self, client: Redis) -> None:
        self.client = client
        self.shas: dict[str, str] = {}

    async def load(self) -> None:
        for name in ("window", "lease", "renew", "release", "budget"):
            source = files("llm_gateway.limits").joinpath("scripts", f"{name}.lua").read_text()
            self.shas[name] = await self.client.script_load(source)

    async def call(
        self, name: str, keys: list[str], args: list[str | int | float]
    ) -> list[int] | int:
        if name not in self.shas:
            await self.load()
        try:
            result: object = await cast(
                Awaitable[object],
                self.client.evalsha(self.shas[name], len(keys), *keys, *[str(arg) for arg in args]),
            )
        except NoScriptError:
            await self.load()
            result = await cast(
                Awaitable[object],
                self.client.evalsha(self.shas[name], len(keys), *keys, *[str(arg) for arg in args]),
            )
        if isinstance(result, list):
            values = cast(list[str | bytes | int], result)
            return [int(value) for value in values]
        return int(cast(str | bytes | int, result))
