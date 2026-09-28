"""Require phone-shaped evidence and exclude date/time components in context."""

import re

DATE_TIME = re.compile(
    r"(?<![0-9])(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|"
    r"[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{2}:[0-9]{2})(?![0-9])"
)
LOCAL_GROUPING = re.compile(r"(?:[0-9]{3}[ -][0-9]{4}|[0-9]{2,3}[ -][0-9]{3}[ -][0-9]{2,3})")
YEAR_SEQUENCE = re.compile(r"[12][0-9]{3}(?:[ \t]+[12][0-9]{3})+")


def is_phone(text: str, start: int, end: int, digits: str) -> bool:
    if not 7 <= len(digits) <= 15:
        return False
    value = text[start:end]
    if YEAR_SEQUENCE.fullmatch(value):
        return False
    if not (value.startswith("+") or len(digits) >= 10 or LOCAL_GROUPING.fullmatch(value)):
        return False
    # Include context so the slash-separated pieces of a date cannot become phones.
    return not any(
        match.start() < end and match.end() > start
        for match in DATE_TIME.finditer(text, max(0, start - 10), min(len(text), end + 10))
    )
