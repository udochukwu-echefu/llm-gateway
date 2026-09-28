"""Keep large inspections off the event loop and wait for safe cleanup on cancellation."""

from collections.abc import Callable
from typing import cast

import anyio
from pydantic import BaseModel

OFFLOAD_CHARACTERS = 32 * 1024


async def inspect_large[T](operation: Callable[[], T], value: object) -> T:
    if _is_large(value):
        # Context (including tracing) propagates. Do not abandon a worker still mutating
        # the request mapping: finalization must wait before clearing sensitive state.
        return await anyio.to_thread.run_sync(operation, abandon_on_cancel=False)
    return operation()


def _is_large(value: object) -> bool:
    pending = [value]
    size = 0
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            size += len(item)
        elif isinstance(item, BaseModel):
            pending.extend(item.__dict__.values())
            if item.model_extra:
                pending.extend(item.model_extra.values())
        elif isinstance(item, dict):
            data = cast(dict[object, object], item)
            pending.extend(data.keys())
            pending.extend(data.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(cast(list[object] | tuple[object, ...], item))
        if size >= OFFLOAD_CHARACTERS:
            return True
    return False
