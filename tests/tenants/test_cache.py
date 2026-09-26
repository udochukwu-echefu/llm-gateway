import uuid

from llm_gateway.tenants.cache import VerifiedKeyCache
from llm_gateway.tenants.repository import KeyRecord


def test_lru_evicts_least_recently_used_entry() -> None:
    cache = VerifiedKeyCache(max_size=2, clock=lambda: 0.0)
    records = [KeyRecord(str(i), bytes(32), uuid.uuid4(), uuid.uuid4()) for i in range(3)]
    cache.put(records[0])
    cache.put(records[1])
    assert cache.get("0") is not None

    cache.put(records[2])

    assert cache.get("1") is None
    assert cache.get("0") == records[0]
    assert cache.get("2") == records[2]
