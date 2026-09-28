from llm_gateway.guardrails.cards import card_spans


def test_longest_valid_group_window_wins() -> None:
    # All-zero synthetic candidates deliberately satisfy Luhn at several lengths.
    text = "0000000000000 000 000"

    assert card_spans(text) == [(0, len(text))]


def test_equal_length_overlapping_windows_prefer_earliest() -> None:
    text = "0000000000 000000000 0000000000"

    assert card_spans(text) == [(0, 20)]


def test_disjoint_cards_in_one_run_are_both_found() -> None:
    text = "4242424242424242 4111111111111111"

    assert card_spans(text) == [(0, 16), (17, 33)]
