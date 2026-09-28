from llm_gateway.guardrails.cards import card_spans


def test_overlapping_valid_windows_redact_union() -> None:
    # Obviously fake all-zero groups satisfy Luhn for overlapping accepted layouts.
    text = "0000 0000 0000 0000 0000"

    assert card_spans(text) == [(0, len(text))]


def test_unrecognized_group_layout_is_not_a_card() -> None:
    text = "0000000000 000000000 0000000000"

    assert card_spans(text) == []


def test_disjoint_cards_in_one_run_are_both_found() -> None:
    text = "4242424242424242 4111111111111111"

    assert card_spans(text) == [(0, 16), (17, 33)]
