import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from llm_gateway.catalog import PricePeriod, load_catalog
from llm_gateway.cost import compute_cost
from llm_gateway.schemas.chat import Usage
from llm_gateway.tenants.auth import Principal
from llm_gateway.usage.record import UsageEvent
from tests.providers.fixtures import HOSTED_USAGE, NVIDIA_MODELS


@pytest.mark.parametrize(
    ("model", "expected"),
    [("glm-5.3-flash", "0.00000704"), ("glm-5.3-flashx", "0.00001754"), ("glm-5.3", "0.00006288")],
)
def test_zai_receipts_use_exact_list_and_cached_prices(model: str, expected: str) -> None:
    catalog = load_catalog()
    price = catalog.find("zai", model, "chat")
    assert price is not None
    event = UsageEvent(
        Principal(uuid.uuid4(), uuid.uuid4(), "fake-key"),
        "request",
        price,
        catalog,
        "chat",
        False,
        requested_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    event.usage = Usage.model_validate(HOSTED_USAGE)

    record = event.finish(1, 1)

    assert record.cost_status == "priced"
    assert type(record.cost_usd) is Decimal
    assert record.cost_usd == Decimal(expected)
    assert record.reasoning_tokens == 3  # Already part of output, not charged twice.


@pytest.mark.parametrize("model", NVIDIA_MODELS)
def test_nvidia_unknown_price_cannot_be_computed_as_zero(model: str) -> None:
    catalog = load_catalog()
    price = catalog.find("nvidia", model, "chat")
    assert price is not None
    assert price.region == "global"
    period = price.at(datetime(2026, 9, 30, tzinfo=UTC))
    assert period is not None
    assert period.unpriced

    with pytest.raises(ValueError, match="model price is unknown"):
        compute_cost(period, 20, 10, 8)


@pytest.mark.parametrize("field", ["input_price", "output_price", "cached_input_price"])
def test_explicit_unpriced_period_cannot_hide_a_price(field: str) -> None:
    catalog = load_catalog()
    price = catalog.find("nvidia", "moonshotai/kimi-k3", "chat")
    assert price is not None
    period = price.periods[0].model_dump()
    period[field] = Decimal(0)

    with pytest.raises(ValidationError, match="unpriced periods must not contain token prices"):
        PricePeriod.model_validate(period)


def test_missing_price_without_explicit_unpriced_flag_is_invalid() -> None:
    price = load_catalog().models[0].periods[0].model_dump()
    price["input_price"] = None

    with pytest.raises(ValidationError, match="priced periods need an input price"):
        PricePeriod.model_validate(price)
