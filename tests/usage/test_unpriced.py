import uuid
from datetime import UTC, datetime

import pytest

from llm_gateway.catalog import Catalog, ModelPrice, load_catalog
from llm_gateway.cost import compute_cost
from llm_gateway.schemas.chat import Usage
from llm_gateway.tenants.auth import Principal
from llm_gateway.usage.record import UsageEvent


def unpriced_model() -> ModelPrice:
    data = load_catalog().models[0].model_dump()
    data["periods"][0].update(
        unpriced=True, input_price=None, output_price=None, cached_input_price=None
    )
    return ModelPrice.model_validate(data)


def test_explicit_unpriced_receipt_keeps_tokens_without_claiming_zero_cost() -> None:
    price = unpriced_model()
    catalog = Catalog(version="synthetic", models=[price])
    event = UsageEvent(
        Principal(uuid.uuid4(), uuid.uuid4(), "fake-key"),
        "request",
        price,
        catalog,
        "chat",
        False,
        requested_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    event.usage = Usage(prompt_tokens=20, completion_tokens=10, total_tokens=30)

    record = event.finish(1, 1)

    assert record.cost_status == "unpriced"
    assert record.cost_usd is None
    assert (record.prompt_tokens, record.completion_tokens) == (20, 10)
    with pytest.raises(ValueError, match="model price is unknown"):
        compute_cost(price.periods[0], 20, 10)


def test_unpriced_model_without_usage_remains_usage_missing() -> None:
    price = unpriced_model()
    event = UsageEvent(
        Principal(uuid.uuid4(), uuid.uuid4(), "fake-key"),
        "request",
        price,
        Catalog(version="synthetic", models=[price]),
        "chat",
        True,
        requested_at=datetime(2026, 9, 30, tzinfo=UTC),
    )

    record = event.finish(1, 1)

    assert record.cost_status == "usage_missing"
    assert record.cost_usd is None
