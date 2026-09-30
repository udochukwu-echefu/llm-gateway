"""Pure USD arithmetic: never convert a token price through a binary float."""

from decimal import Decimal

from llm_gateway.catalog import PricePeriod


def compute_cost(
    price: PricePeriod, prompt_tokens: int, completion_tokens: int = 0, cached_tokens: int = 0
) -> Decimal:
    if price.unpriced or price.input_price is None:
        raise ValueError("model price is unknown")
    if min(prompt_tokens, completion_tokens, cached_tokens) < 0 or cached_tokens > prompt_tokens:
        raise ValueError("invalid token counts")
    return (
        (prompt_tokens - cached_tokens) * price.input_price
        + cached_tokens
        * (price.cached_input_price if price.cached_input_price is not None else price.input_price)
        + completion_tokens * (price.output_price or Decimal(0))
    ) / Decimal(1_000_000)
