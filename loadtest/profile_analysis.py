"""Rank exclusive stack samples, rather than calling wide parent frames CPU hotspots."""

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from loadtest.runtime import ROOT


@dataclass(frozen=True)
class Frame:
    name: str
    samples: int
    x: float
    y: float
    width: float


def exclusive_hotspots(frames: list[Frame], limit: int = 3) -> list[tuple[str, int]]:
    totals: Counter[str] = Counter()
    root_y = next(frame.y for frame in frames if frame.name == "all")
    levels = sorted({frame.y for frame in frames})
    if root_y == levels[-1]:
        levels.reverse()
    for frame in frames:
        index = levels.index(frame.y)
        child_y = levels[index + 1] if index + 1 < len(levels) else None
        child_samples = sum(
            child.samples
            for child in frames
            if child.y == child_y
            and child.x >= frame.x - 0.001
            and child.x + child.width <= frame.x + frame.width + 0.001
        )
        exclusive = max(0, frame.samples - child_samples)
        if frame.name != "all" and exclusive:
            totals[frame.name] += exclusive
    return totals.most_common(limit)


def read_frames(path: Path) -> list[Frame]:
    namespace = "{http://www.w3.org/2000/svg}"
    frames: list[Frame] = []
    # Only read the local SVG emitted by our py-spy command, never uploaded/untrusted XML.
    for group in ET.parse(path).getroot().iter(f"{namespace}g"):  # noqa: S314
        title, rectangle = group.find(f"{namespace}title"), group.find(f"{namespace}rect")
        if title is None or rectangle is None or title.text is None:
            continue
        match = re.fullmatch(r"(.*) \(([\d,]+) samples, [\d.]+%\)", title.text)
        if match is not None:
            frames.append(
                Frame(
                    match[1],
                    int(match[2].replace(",", "")),
                    float(rectangle.attrib["x"].rstrip("%")),
                    float(rectangle.attrib["y"]),
                    float(rectangle.attrib["width"].rstrip("%")),
                )
            )
    if not frames:
        raise ValueError("No sampled frames in py-spy SVG")
    return frames


if __name__ == "__main__":
    directory = ROOT / "docs/benchmarks"
    frames = read_frames(directory / "S1-flamegraph.svg")
    result = {
        "top_exclusive_samples": exclusive_hotspots(frames),
        "total_samples": max(frame.samples for frame in frames),
    }
    (directory / "hotspots.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
