import time

import pytest

from llm_gateway.guardrails.detectors import scan
from llm_gateway.guardrails.policy import Detector


@pytest.mark.parametrize(
    ("detector", "positive", "negative"),
    [
        ("secret_api_key", "sk-" + "FAKE" * 8, "sk-short"),
        ("secret_api_key", "gsk_" + "FAKE" * 8, "gsk_short"),
        ("secret_api_key", "AIza" + "F" * 35, "AIzaSHORT"),
        ("secret_api_key", "ghp_" + "F" * 36, "ghp_short"),
        ("secret_api_key", "AKIA" + "F" * 16, "AKIAshort"),
        ("secret_api_key", "lgw_aaaaaaaaaaaa_" + "F" * 43, "lgw_bad_short"),
        (
            "secret_private_key",
            "-----BEGIN PRIVATE KEY-----\nRkFLRQ==\n-----END PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----\nFAKE",
        ),
        ("email", "ada@example.com", "ada@localhost"),
        ("phone", "+1 (415) 555-0100", "12345"),
        ("phone", "0801 234 5678", "12345678901234567890"),
        ("card_number", "4242 4242 4242 4242", "4242 4242 4242 4243"),
        ("card_number", "4111-1111-1111-1111", "1234567890123456"),
        ("iban", "GB82 WEST 1234 5698 7654 32", "GB83 WEST 1234 5698 7654 32"),
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
