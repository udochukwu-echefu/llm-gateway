import uuid
from datetime import UTC, datetime
from decimal import Decimal

from llm_gateway.catalog import load_catalog
from llm_gateway.schemas.chat import Usage
from llm_gateway.tenants.auth import Principal
from llm_gateway.usage.record import UsageEvent


def test_gemini_request_selects_price_at_start_even_if_it_finishes_after_midnight() -> None:
    catalog = load_catalog()
    price = catalog.find("gemini", "gemini-3.8-flash", "chat")
    assert price is not None
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "test-key")
    before = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    after = datetime(2027, 1, 1, tzinfo=UTC)
    old = UsageEvent(principal, "old", price, catalog, "chat", True, requested_at=before)
    new = UsageEvent(principal, "new", price, catalog, "chat", True, requested_at=after)
    usage = Usage(prompt_tokens=10, completion_tokens=2, total_tokens=12)
    old.usage = new.usage = usage

    old_record = old.finish(2000, 100)
    new_record = new.finish(1, 1)

    assert old_record.created_at == before
    assert new_record.created_at == after
    assert old_record.cost_usd is not None
    assert new_record.cost_usd is not None
    assert old_record.cost_usd == Decimal("0.0000150")
    assert new_record.cost_usd == Decimal("0.0000300")
    assert old_record.cost_usd * 2 == new_record.cost_usd
    assert old_record.catalog_version == new_record.catalog_version == catalog.version
