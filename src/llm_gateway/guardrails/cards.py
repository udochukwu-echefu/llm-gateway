"""Check whole digit groups, never arbitrary substrings of long tracking numbers."""

import re
from collections import deque
from dataclasses import dataclass

GROUP = re.compile(r"[0-9]+")
LAYOUTS = ((4, 4, 4, 4), (4, 6, 5), (4, 6, 4), (4, 4, 4, 4, 3))
LAYOUTS_BY_END = {
    length: tuple(shape for shape in LAYOUTS if shape[-1] == length) for length in (3, 4, 5)
}


@dataclass(slots=True)
class DigitGroup:
    start: int
    end: int
    length: int
    normal: int
    flipped: int


def card_spans(value: str) -> list[tuple[int, int]]:
    if any(char not in "0123456789 -\t" for char in value):
        return []
    groups: deque[DigitGroup] = deque(maxlen=5)
    candidates: list[tuple[int, int]] = []
    for group in GROUP.finditer(value):
        length = group.end() - group.start()
        if 13 <= length <= 19 and luhn(group.group()):
            candidates.append((group.start(), group.end()))
        if length not in (3, 4, 5, 6):
            groups.clear()
            continue
        groups.append(_digit_group(group))
        for layout in LAYOUTS_BY_END.get(length, ()):
            if len(groups) < len(layout):
                continue
            window = list(groups)[-len(layout) :]
            if tuple(item.length for item in window) != layout:
                continue
            if _valid_window(window):
                candidates.append((window[0].start, group.end()))
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


def _digit_group(match: re.Match[str]) -> DigitGroup:
    normal, flipped = 0, 0
    for index, char in enumerate(reversed(match.group())):
        digit = ord(char) - 48
        doubled = digit * 2 - (9 if digit >= 5 else 0)
        normal += doubled if index % 2 else digit
        flipped += digit if index % 2 else doubled
    return DigitGroup(match.start(), match.end(), match.end() - match.start(), normal, flipped)


def _valid_window(groups: list[DigitGroup]) -> bool:
    total, length = 0, 0
    for group in reversed(groups):
        total += group.flipped if length % 2 else group.normal
        length += group.length
    return total % 10 == 0
