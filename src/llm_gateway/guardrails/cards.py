"""Check whole digit groups, never arbitrary substrings of long tracking numbers."""

import re

GROUP = re.compile(r"[0-9]+")


def card_spans(value: str) -> list[tuple[int, int]]:
    if any(char not in "0123456789 -\t" for char in value):
        return []
    groups = list(GROUP.finditer(value))
    candidates: list[tuple[int, int, int]] = []
    for start in range(len(groups)):
        digits = ""
        for end in range(start, min(start + 19, len(groups))):
            if len(digits) + len(groups[end].group()) > 19:
                break
            digits += groups[end].group()
            if len(digits) >= 13 and luhn(digits):
                candidates.append((len(digits), start, end))
    occupied: set[int] = set()
    spans: list[tuple[int, int]] = []
    for _, start, end in sorted(candidates, key=lambda item: (-item[0], item[1])):
        indices = range(start, end + 1)
        if any(index in occupied for index in indices):
            continue
        occupied.update(indices)
        spans.append((groups[start].start(), groups[end].end()))
    return sorted(spans)


def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0
