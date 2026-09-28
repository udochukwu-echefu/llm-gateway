"""Obviously fake data: reserved domains/IPs and published payment examples only."""

from typing import Any

from tests.fixtures import CHAT_REQUEST, COMPLETION

EMAIL = "ada@example.com"
OTHER_EMAIL = "grace@example.com"
FAKE_KEY = "sk-" + "FAKE" * 8
FAKE_GATEWAY_KEY = "lgw_aaaaaaaaaaaa_" + "F" * 43
FAKE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nRkFLRQ==\n-----END PRIVATE KEY-----"
# Stripe's published test Visa: https://docs.stripe.com/testing#cards
CARD = "4242 4242 4242 4242"
CARD_CONTEXTS = (
    ("Card 4111 1111 1111 1111 123 please", "4111 1111 1111 1111"),
    ("My card is 4242424242424242 1227", "4242424242424242"),
    ("ref 99 4242424242424242 1227", "4242424242424242"),
    ("| 99\t4242424242424242\t1227 |", "4242424242424242"),
)
# SWIFT's documented GB example: https://www.swift.com/standards/data-standards/iban
IBAN = "GB82 WEST 1234 5698 7654 32"


def prompt(text: str, *, stream: bool = False) -> dict[str, Any]:
    return {**CHAT_REQUEST, "stream": stream, "messages": [{"role": "user", "content": text}]}


def completion(text: str) -> dict[str, Any]:
    return {
        **COMPLETION,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
    }


def chunks(parts: list[str], field: str = "content") -> list[dict[str, Any]]:
    return [
        {
            "id": "fake-chunk",
            "model": "model",
            "choices": [{"index": 0, "delta": {field: part}, "finish_reason": None}],
        }
        for part in parts
    ] + [
        {
            "id": "fake-chunk",
            "model": "model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    ]
