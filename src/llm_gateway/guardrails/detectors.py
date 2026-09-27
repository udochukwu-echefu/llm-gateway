"""Pure span detection. Bounded candidates avoid ambiguous unbounded regex repetition."""

import ipaddress
import re
from dataclasses import dataclass

from llm_gateway.guardrails.policy import Detector


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    detector: Detector


KEY = re.compile(
    r"(?<![\w-])(?:sk-[A-Za-z0-9_-]{20,256}|gsk_[A-Za-z0-9]{20,128}|"
    r"AIza[A-Za-z0-9_-]{35}|ghp_[A-Za-z0-9]{36}|AKIA[A-Z0-9]{16}|"
    r"lgw_[a-z2-7]{12}_[A-Za-z0-9_-]{43})(?![\w-])"
)
PRIVATE = re.compile(
    r"-----BEGIN (?P<label>(?:[A-Z0-9]{1,16} )?PRIVATE KEY)-----"
    r"(?:(?!-----BEGIN |-----END ).)++-----END (?P=label)-----",
    re.DOTALL,
)
EMAIL = re.compile(
    r"(?<![\w.+%-])[A-Za-z0-9_+%-][A-Za-z0-9_.+%-]{0,63}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,63}(?![\w-]|\.[A-Za-z0-9])"
)
NUMBER = re.compile(r"(?<![\w+])\+?[0-9][0-9 ()-]*+")
IBAN = re.compile(r"(?<!\w)[A-Z]{2}[0-9]{2}(?: ?[A-Z0-9]){11,30}(?![A-Z0-9])")
IP = re.compile(r"(?<![\w.:])[0-9A-Fa-f:.]{2,45}(?![\w.:])")


def scan(text: str) -> list[Finding]:
    findings: list[Finding] = []
    patterns: tuple[tuple[re.Pattern[str], Detector], ...] = (
        (KEY, "secret_api_key"),
        (PRIVATE, "secret_private_key"),
        (EMAIL, "email"),
    )
    for pattern, detector in patterns:
        findings.extend(Finding(m.start(), m.end(), detector) for m in pattern.finditer(text))
    for match in NUMBER.finditer(text):
        value = match.group().rstrip(" ()-")
        end = match.start() + len(value)
        digits = "".join(c for c in value if c.isascii() and c.isdigit())
        if 13 <= len(digits) <= 19 and all(c in "0123456789 -" for c in value) and luhn(digits):
            findings.append(Finding(match.start(), end, "card_number"))
        if 7 <= len(digits) <= 15:
            findings.append(Finding(match.start(), end, "phone"))
    for match in IBAN.finditer(text):
        candidate = match.group()
        # Uppercase prose after a spaced IBAN is not part of the account number.
        ends = [i for i in range(15, len(candidate)) if candidate[i] == " "] + [len(candidate)]
        for end in reversed(ends):
            if valid_iban(candidate[:end]):
                findings.append(Finding(match.start(), match.start() + end, "iban"))
                break
    for match in IP.finditer(text):
        candidate = match.group().rstrip(".")
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        findings.append(Finding(match.start(), match.start() + len(candidate), "ip_address"))
    return sorted(findings, key=lambda f: (f.start, -f.end, f.detector))


def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def valid_iban(value: str) -> bool:
    compact = value.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    remainder = 0
    for char in compact[4:] + compact[:4]:
        for digit in str(ord(char) - 55) if char.isalpha() else char:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1
