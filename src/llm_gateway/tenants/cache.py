"""Bounded, successful-verification-only LRU with a monotonic injectable clock."""

import time
from collections import OrderedDict
from collections.abc import Callable

from llm_gateway.tenants.repository import KeyRecord


class VerifiedKeyCache:
    def __init__(
        self, ttl: float = 30, max_size: int = 10_000, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.ttl = ttl
        self.max_size = max_size
        self.clock = clock
        self.entries: OrderedDict[str, tuple[float, KeyRecord]] = OrderedDict()

    def get(self, key_id: str) -> KeyRecord | None:
        entry = self.entries.get(key_id)
        if entry is None:
            return None
        expires, record = entry
        if self.clock() >= expires:
            del self.entries[key_id]
            return None
        self.entries.move_to_end(key_id)
        return record

    def put(self, record: KeyRecord) -> None:
        if self.ttl <= 0 or self.max_size <= 0:
            return
        self.entries[record.key_id] = (self.clock() + self.ttl, record)
        self.entries.move_to_end(record.key_id)
        if len(self.entries) > self.max_size:
            self.entries.popitem(last=False)
