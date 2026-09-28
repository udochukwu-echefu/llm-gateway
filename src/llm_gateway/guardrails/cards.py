"""Check whole digit groups, never arbitrary substrings of long tracking numbers."""

import re

GROUP = re.compile(r"[0-9]+")
LAYOUTS = ((4, 4, 4, 4), (4, 6, 5), (4, 6, 4), (4, 4, 4, 4, 3))


def card_spans(value: str) -> list[tuple[int, int]]:
    if any(char not in "0123456789 -\t" for char in value):
        return []
    groups = list(GROUP.finditer(value))
    candidates: list[tuple[int, int]] = []
    for start, group in enumerate(groups):
        if 13 <= len(group.group()) <= 19 and luhn(group.group()):
            candidates.append((group.start(), group.end()))
        if len(group.group()) != 4:
            continue
        for layout in LAYOUTS:
            window = groups[start : start + len(layout)]
            if tuple(len(item.group()) for item in window) != layout:
                continue
            if luhn("".join(item.group() for item in window)):
                candidates.append((group.start(), window[-1].end()))
    spans: list[tuple[int, int]] = []
    for start, end in sorted(candidates):
        if spans and start < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
        else:
            spans.append((start, end))
    return spans


def luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0
