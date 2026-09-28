import time

import pytest

from llm_gateway.guardrails.detectors import scan
from llm_gateway.guardrails.policy import Detector
from tests.guardrails.fixtures import (
    CARD,
    CARD_CONTEXTS,
    EMAIL,
    FAKE_GATEWAY_KEY,
    FAKE_KEY,
    FAKE_PRIVATE_KEY,
    IBAN,
)


@pytest.mark.parametrize(
    ("detector", "positive", "negative"),
    [
        ("secret_api_key", FAKE_KEY, "sk-short"),
        ("secret_api_key", "gsk_" + "FAKE" * 8, "gsk_short"),
        ("secret_api_key", "AIza" + "F" * 35, "AIzaSHORT"),
        ("secret_api_key", "ghp_" + "F" * 36, "ghp_short"),
        ("secret_api_key", "AKIA" + "F" * 16, "AKIAshort"),
        ("secret_api_key", FAKE_GATEWAY_KEY, "lgw_bad_short"),
        (
            "secret_private_key",
            FAKE_PRIVATE_KEY,
            "-----BEGIN PRIVATE KEY-----\nFAKE",
        ),
        ("email", EMAIL, "ada@localhost"),
        ("phone", "+1 (415) 555-0100", "12345"),
        ("phone", "07700 900123", "12345678901234567890"),
        ("card_number", CARD, "4242 4242 4242 4243"),
        ("card_number", "4111-1111-1111-1111", "1234567890123456"),
        ("iban", IBAN, "GB83 WEST 1234 5698 7654 32"),
        ("ip_address", "192.0.2.1", "999.0.2.1"),
        ("ip_address", "2001:db8::1", "2001:db8::gg"),
    ],
)
def test_detector_true_and_false_positives(
    detector: Detector, positive: str, negative: str
) -> None:
    found = [finding for finding in scan(positive) if finding.detector == detector]

    assert any(positive[f.start : f.end] == positive for f in found)
    assert not any(f.detector == detector for f in scan(negative))


@pytest.mark.parametrize(
    "text",
    [
        "a@a.a@a" * 15000,
        "1" * 100000,
        "a" * 100000,
        "1 " * 50000,
        "-----BEGIN PRIVATE KEY-----\n" * 4000,
    ],
)
def test_adversarial_scan_has_small_time_bound(text: str) -> None:
    started = time.monotonic()

    scan(text)

    assert time.monotonic() - started < 1


@pytest.mark.parametrize(
    ("text", "detector", "value"),
    [
        (f"Hello {EMAIL}.", "email", EMAIL),
        ("Address: 192.0.2.1.", "ip_address", "192.0.2.1"),
        (IBAN + " PLEASE PAY", "iban", IBAN),
        (
            "-----BEGIN DSA PRIVATE KEY-----\nRkFLRQ==\n-----END DSA PRIVATE KEY-----",
            "secret_private_key",
            "-----BEGIN DSA PRIVATE KEY-----\nRkFLRQ==\n-----END DSA PRIVATE KEY-----",
        ),
    ],
)
def test_detector_boundaries(text: str, detector: Detector, value: str) -> None:
    assert any(f.detector == detector and text[f.start : f.end] == value for f in scan(text))


@pytest.mark.parametrize(("text", "card"), CARD_CONTEXTS)
def test_card_adjacent_to_other_digit_groups(text: str, card: str) -> None:
    found = [text[f.start : f.end] for f in scan(text) if f.detector == "card_number"]

    assert found == [card]


@pytest.mark.parametrize(
    "text",
    [
        "123456789012345678901234567890",
        "99 4242424242424243 1227",
        "4111 1111 1111 1112 123",
    ],
)
def test_invalid_card_groups_and_unseparated_tracking_numbers(text: str) -> None:
    assert not any(f.detector == "card_number" for f in scan(text))
