from decimal import Decimal

import pytest

from llm_gateway.catalog import load_catalog
from llm_gateway.cost import compute_cost


@pytest.mark.parametrize(
    ("model", "prompt", "output", "cached", "expected"),
    [
        ("gpt-4.1-nano", 3, 2, 0, "0.00000110"),
        ("gpt-4.1-nano", 10, 2, 4, "0.00000150"),
        ("openai/gpt-oss-20b", 10, 2, 4, "0.00000135"),
        ("openai/gpt-oss-20b", 0, 10, 0, "0.0000030"),
        ("text-embedding-3-small", 3, 0, 0, "0.00000006"),
        ("gpt-4.1-nano", 0, 0, 0, "0"),
    ],
)
def test_cost_exact_in_decimal(
    model: str, prompt: int, output: int, cached: int, expected: str
) -> None:
    price = next(entry for entry in load_catalog().models if entry.model == model).periods[0]

    result = compute_cost(price, prompt, output, cached)

    assert type(result) is Decimal
    assert result == Decimal(expected)


def test_cached_tokens_cannot_exceed_prompt_tokens() -> None:
    price = load_catalog().models[0].periods[0]

    with pytest.raises(ValueError, match="invalid token counts"):
        compute_cost(price, 1, cached_tokens=2)


def test_free_cached_tokens_are_not_charged_at_input_rate() -> None:
    price = (
        load_catalog().models[0].periods[0].model_copy(update={"cached_input_price": Decimal(0)})
    )

    assert compute_cost(price, 10, cached_tokens=4) == Decimal("0.00000045")
