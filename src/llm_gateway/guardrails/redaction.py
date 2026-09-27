"""Sensitive mappings live only in their request; substitution is non-recursive."""

import re
from collections import Counter

from llm_gateway.guardrails.detectors import Finding

PLACEHOLDER = re.compile(r"\[(?:OUTPUT_)?[A-Z_]+_[0-9]+\]")


class Redactor:
    def __init__(self, *, output: bool = False) -> None:
        self.originals: dict[str, str] = {}
        self.tokens: dict[tuple[str, str], str] = {}
        self.reserved: set[str] = set()
        self.counts: Counter[str] = Counter()
        self.output = output

    def reserve(self, text: str) -> str:
        self.reserved.update(PLACEHOLDER.findall(text))
        return text

    def redact(self, text: str, findings: list[Finding]) -> tuple[str, int]:
        pieces: list[str] = []
        end, count = 0, 0
        for finding in sorted(findings, key=lambda f: (f.start, -f.end)):
            if finding.start < end:
                continue
            pieces.extend((text[end : finding.start], self._token(text, finding)))
            end = finding.end
            count += 1
        pieces.append(text[end:])
        return "".join(pieces), count

    def restore(self, text: str) -> str:
        return PLACEHOLDER.sub(lambda m: self.originals.get(m.group(), m.group()), text)

    def _token(self, text: str, finding: Finding) -> str:
        original = text[finding.start : finding.end]
        key = (finding.detector, original)
        if key in self.tokens:
            return self.tokens[key]
        label = ("OUTPUT_" if self.output else "") + finding.detector.upper()
        while True:
            self.counts[label] += 1
            token = f"[{label}_{self.counts[label]}]"
            if token not in self.reserved:
                break
        self.tokens[key] = token
        self.originals[token] = original
        return token


class RestoreBuffer:
    """Only an unfinished prefix of an actual request placeholder is held back."""

    def __init__(self, redactor: Redactor) -> None:
        self.redactor = redactor
        self.pending = ""
        self.prefixes = {token[:i] for token in redactor.originals for i in range(1, len(token))}

    def push(self, text: str, *, final: bool = False) -> str:
        value = self.pending + text
        self.pending = ""
        if not final:
            start = value.rfind("[")
            if start >= 0 and value[start:] in self.prefixes:
                self.pending, value = value[start:], value[:start]
        return self.redactor.restore(value)
